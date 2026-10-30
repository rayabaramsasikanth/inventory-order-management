from urllib.parse import urlparse, parse_qs

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.core.idempotency import execute_idempotently
from apps.core.models import IdempotencyRecord
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class EmailVerificationAndAccountLifecycleTests(APITestCase):
    def setUp(self):
        cache.clear()

    def register(self, username="verify-user", email="verify@example.com"):
        return self.client.post(
            "/api/auth/register/",
            {"username": username, "email": email, "password": "StrongPass!927"},
            format="json",
        )

    def test_registration_requires_email_verification_before_login(self):
        response = self.register()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="verify-user")
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)

        login = self.client.post(
            "/api/auth/login/",
            {"username": "verify-user", "password": "StrongPass!927"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_verification_token_enables_login(self):
        self.register()
        body = mail.outbox[-1].body
        query = parse_qs(urlparse(body.split()[-1]).query)
        response = self.client.post(
            "/api/auth/verify-email/",
            {"uid": query["uid"][0], "token": query["token"][0]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(username="verify-user")
        self.assertTrue(user.email_verified)

        login = self.client.post(
            "/api/auth/login/",
            {"username": "verify-user", "password": "StrongPass!927"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_deactivation_requires_password_and_disables_account(self):
        user = User.objects.create_user(
            username="deactivate-user", email="deactivate@example.com",
            password="StrongPass!927",
        )
        self.client.force_authenticate(user=user)
        response = self.client.post(
            "/api/auth/deactivate/", {"password": "StrongPass!927"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertFalse(user.is_active)


class ProductCatalogStructureTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="catalog-admin", password="StrongPass!927", is_superuser=True
        )
        self.client.force_authenticate(user=self.admin)

    def test_admin_can_create_category_and_unit_of_measure(self):
        category = self.client.post(
            "/api/catalog/categories/",
            {"name": "Electronics", "slug": "electronics", "description": "Devices"},
            format="json",
        )
        self.assertEqual(category.status_code, status.HTTP_201_CREATED)

        unit = self.client.post(
            "/api/catalog/units/",
            {"code": "BOX", "name": "Box", "decimal_places": 0},
            format="json",
        )
        self.assertEqual(unit.status_code, status.HTTP_201_CREATED)


class IdempotencyTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="idempotency-user", password="StrongPass!927")
        self.factory = APIRequestFactory()

    def build_request(self, data):
        raw = self.factory.post(
            "/api/test-write/", data, format="json",
            HTTP_IDEMPOTENCY_KEY="test-idempotency-key",
        )
        force_authenticate(raw, user=self.user)
        return APIView().initialize_request(raw)

    def test_same_key_and_payload_replays_stored_response(self):
        calls = {"count": 0}

        def operation():
            calls["count"] += 1
            return Response({"created_id": 42}, status=201)

        first = execute_idempotently(self.build_request({"amount": 3}), operation)
        second = execute_idempotently(self.build_request({"amount": 3}), operation)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data, {"created_id": 42})
        self.assertEqual(calls["count"], 1)
        self.assertEqual(IdempotencyRecord.objects.count(), 1)

    def test_same_key_with_different_payload_returns_conflict(self):
        execute_idempotently(
            self.build_request({"amount": 3}),
            lambda: Response({"created_id": 42}, status=201),
        )
        response = execute_idempotently(
            self.build_request({"amount": 4}),
            lambda: Response({"created_id": 43}, status=201),
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
