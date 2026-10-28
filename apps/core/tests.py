
from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken


# Use the custom user model configured in Django settings.
User = get_user_model()


class HealthCheckTests(APITestCase):
    def test_health_check_returns_healthy_status(self):
        # Call the public health endpoint.
        response = self.client.get("/api/health/")

        # Confirm that the API responds successfully with the expected data.
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

        # Registration should create the account and return HTTP 201.
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="testuser").exists())

        # Verify that Django stored a hashed password, not the raw password.
        user = User.objects.get(username="testuser")
        self.assertTrue(user.check_password("StrongPass!927"))

        # Ensure the API never exposes the password in its response.
        self.assertNotIn("password", response.data)

    def test_registration_rejects_duplicate_username(self):
        # Create an account before attempting to register the same username.
        User.objects.create_user(
            username="testuser",
            email="first@example.com",
            password="StrongPass!927",
        )

        # Attempt to register another account with the existing username.
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "testuser",
                "email": "second@example.com",
                "password": "StrongPass!927",
            },
            format="json",
        )

        # Duplicate usernames should be rejected with HTTP 400.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AuthenticationTests(APITestCase):
    def setUp(self):
        # Create a fresh test user for each authentication test.
        self.user = User.objects.create_user(
            username="authuser",
            email="auth@example.com",
            password="StrongPass!927",
        )

    def test_login_returns_access_and_refresh_tokens(self):
        # Submit valid credentials to the SimpleJWT login endpoint.
        response = self.client.post(
            "/api/auth/login/",
            {
                "username": "authuser",
                "password": "StrongPass!927",
            },
            format="json",
        )

        # A successful login must return both token types.
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_profile_requires_authentication(self):
        # Make a request without providing a JWT access token.
        response = self.client.get("/api/auth/profile/")

        # Anonymous requests must not access the protected profile.
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_logout_blacklists_refresh_token(self):
        # Generate a refresh token for the test user.
        refresh = RefreshToken.for_user(self.user)

        # Simulate an authenticated request to the logout endpoint.
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/auth/logout/",
            {"refresh": str(refresh)},
            format="json",
        )

        # Logout should succeed and blacklist the supplied token.
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # SimpleJWT should reject the blacklisted token.
        with self.assertRaises(TokenError):
            RefreshToken(str(refresh))
