from rest_framework.test import APITestCase
from rest_framework import status

# Create your tests here.
class HealthCheckTests(APITestCase):
    def test_health_check_returns_healthy_status(self):
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "healthy")
        self.assertEqual(
            response.data["Service"],
            "inventory-order-management",
        )