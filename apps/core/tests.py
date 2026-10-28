
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command, CommandError

from rest_framework import status
from rest_framework.test import APITestCase, APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.permissions import (
    ADMIN_GROUP,
    WAREHOUSE_GROUP,
    SALES_GROUP,
    IsAdminUser,
    IsWarehouseStaff,
    IsSalesStaff,
)


# Use the custom user model configured in Django settings.
User = get_user_model()


class HealthCheckTests(APITestCase):
    def test_health_check_returns_healthy_status(self):
        # Call the public health endpoint.
        response = self.client.get("/api/health/")

        # Confirm that the API responds with the expected data.
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "healthy")
        self.assertEqual(
            response.data["service"],
            "inventory-order-management",
        )


class RegistrationTests(APITestCase):
    def test_register_user_successfully(self):
        # Submit valid registration data as JSON.
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "testuser",
                "email": "test@example.com",
                "password": "StrongPass!927",
            },
            format="json",
        )

        # A successful registration should return HTTP 201.
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="testuser").exists())

        # Verify that Django stored a hashed password.
        user = User.objects.get(username="testuser")
        self.assertTrue(user.check_password("StrongPass!927"))

        # The API must never return the user's password.
        self.assertNotIn("password", response.data)

    def test_registration_rejects_duplicate_username(self):
        # Create an account before attempting a duplicate registration.
        User.objects.create_user(
            username="testuser",
            email="first@example.com",
            password="StrongPass!927",
        )

        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "testuser",
                "email": "second@example.com",
                "password": "StrongPass!927",
            },
            format="json",
        )

        # Duplicate usernames should be rejected.
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )


class AuthenticationTests(APITestCase):
    def setUp(self):
        # Create an isolated user for each authentication test.
        self.user = User.objects.create_user(
            username="authuser",
            email="auth@example.com",
            password="StrongPass!927",
        )

    def test_login_returns_access_and_refresh_tokens(self):
        # Submit valid credentials to the login endpoint.
        response = self.client.post(
            "/api/auth/login/",
            {
                "username": "authuser",
                "password": "StrongPass!927",
            },
            format="json",
        )

        # A successful login should return both JWT token types.
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_profile_requires_authentication(self):
        # Request the profile without an access token.
        response = self.client.get("/api/auth/profile/")

        # Anonymous requests must be rejected.
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_logout_blacklists_refresh_token(self):
        # Generate a refresh token for the test user.
        refresh = RefreshToken.for_user(self.user)

        # Simulate an authenticated logout request.
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/auth/logout/",
            {"refresh": str(refresh)},
            format="json",
        )

        # Logout should succeed and blacklist the refresh token.
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # The blacklisted token should no longer be accepted.
        with self.assertRaises(TokenError):
            RefreshToken(str(refresh))


class RolePermissionTests(APITestCase):
    def setUp(self):
        # Create a user for role-based permission checks.
        self.user = User.objects.create_user(
            username="roleuser",
            email="role@example.com",
            password="StrongPass!927",
        )

        # Ensure all required role groups exist.
        self.admin_group, _ = Group.objects.get_or_create(
            name=ADMIN_GROUP
        )
        self.warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )
        self.sales_group, _ = Group.objects.get_or_create(
            name=SALES_GROUP
        )

        # Build test requests without starting a web server.
        self.factory = APIRequestFactory()

    def check_permission(self, permission_class, user=None):
        # Create a request to simulate access to a protected endpoint.
        raw_request = self.factory.get("/api/test/")

        # Authenticate the request when a user is supplied.
        if user is not None:
            force_authenticate(raw_request, user=user)

        # Prepare the request in the same format DRF uses for views.
        view = APIView()
        request = view.initialize_request(raw_request)

        # Evaluate the requested permission class.
        return permission_class().has_permission(request, view)

    def test_admin_group_allows_admin_access(self):
        # Admin group membership should grant admin-level access.
        self.user.groups.add(self.admin_group)

        self.assertTrue(
            self.check_permission(IsAdminUser, self.user)
        )

    def test_warehouse_group_allows_warehouse_access(self):
        # Warehouse staff should pass the warehouse permission check.
        self.user.groups.add(self.warehouse_group)

        self.assertTrue(
            self.check_permission(IsWarehouseStaff, self.user)
        )

    def test_sales_group_allows_sales_access(self):
        # Sales staff should pass the sales permission check.
        self.user.groups.add(self.sales_group)

        self.assertTrue(
            self.check_permission(IsSalesStaff, self.user)
        )

    def test_warehouse_staff_cannot_access_admin_permission(self):
        # Warehouse membership must not grant admin access.
        self.user.groups.add(self.warehouse_group)

        self.assertFalse(
            self.check_permission(IsAdminUser, self.user)
        )

    def test_anonymous_user_is_denied_warehouse_access(self):
        # Anonymous users must not access warehouse operations.
        self.assertFalse(
            self.check_permission(IsWarehouseStaff)
        )


class AssignRoleCommandTests(APITestCase):
    def setUp(self):
        # Create a fresh user for the management command tests.
        self.user = User.objects.create_user(
            username="rolecommanduser",
            email="rolecommand@example.com",
            password="StrongPass!927",
        )

        # Ensure the required group exists in the test database.
        self.group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )

    def test_assign_role_to_existing_user(self):
        # Capture command output so the test can inspect the result.
        output = StringIO()

        call_command(
            "assign_role",
            "rolecommanduser",
            WAREHOUSE_GROUP,
            stdout=output,
        )

        # Verify that the user's group membership was saved.
        self.assertTrue(
            self.user.groups.filter(name=WAREHOUSE_GROUP).exists()
        )
        self.assertIn("Assigned", output.getvalue())

    def test_assign_role_rejects_unknown_username(self):
        # An unknown user should cause a clear management command error.
        with self.assertRaises(CommandError):
            call_command(
                "assign_role",
                "missinguser",
                WAREHOUSE_GROUP,
            )

        # The command must not create an account automatically.
        self.assertFalse(
            User.objects.filter(username="missinguser").exists()
        )
