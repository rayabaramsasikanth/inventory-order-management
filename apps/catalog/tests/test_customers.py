from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import (
    Supplier,
    Product,
    Warehouse,
    Inventory,
    StockMovement,
    Order,
    OrderItem,
    Customer,
)

from apps.catalog.services import (
    record_stock_movement,
    reserve_stock,
    release_reserved_stock,
    transfer_stock,
    create_order,
    cancel_order,
    fulfil_order,
    reconcile_stock,
)

from apps.core.permissions import ADMIN_GROUP, WAREHOUSE_GROUP
from unittest.mock import patch
from decimal import Decimal
from apps.catalog.services import update_order_status

from django.urls import reverse
from apps.core.permissions import SALES_GROUP

User = get_user_model()


class CustomerAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="customer_admin",
            email="admin@example.com",
            password="TestPass123!",
        )

        self.regular_user = User.objects.create_user(
            username="customer_user",
            email="user@example.com",
            password="TestPass123!",
        )

        self.customer_one = Customer.objects.create(
            name="Alpha Stores",
            email="alpha@example.com",
            phone="9876543210",
            is_active=True,
        )

        self.customer_two = Customer.objects.create(
            name="Beta Stores",
            email="beta@example.com",
            phone="9876543211",
            is_active=False,
        )

        self.list_url = "/api/catalog/customers/"

    def test_authenticated_user_can_list_customers(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 2)

    def test_unauthenticated_user_cannot_list_customers(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_only_business_admin_can_create_customer(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            self.list_url,
            {
                "name": "New Customer",
                "email": "new@example.com",
                "phone": "9876543212",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertFalse(
            Customer.objects.filter(name="New Customer").exists()
        )

    def test_admin_can_create_customer(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.list_url,
            {
                "name": "New Customer",
                "email": "new@example.com",
                "phone": "9876543212",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertTrue(
            Customer.objects.filter(name="New Customer").exists()
        )

    def test_filter_customers_by_active_status(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(
            self.list_url,
            {"is_active": "true"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["name"],
            "Alpha Stores",
        )

    def test_search_customers_by_name(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get(
            self.list_url,
            {"search": "Beta"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["name"],
            "Beta Stores",
        )


    def test_regular_user_cannot_update_customer(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.patch(
            f"{self.list_url}{self.customer_one.pk}/",
            {"name": "Unauthorized Update"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.customer_one.refresh_from_db()
        self.assertEqual(self.customer_one.name, "Alpha Stores")

    def test_sales_staff_can_update_customer(self):
        sales_group, _ = Group.objects.get_or_create(name=SALES_GROUP)
        self.regular_user.groups.add(sales_group)
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.patch(
            f"{self.list_url}{self.customer_one.pk}/",
            {"name": "Updated Alpha Stores"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.customer_one.refresh_from_db()
        self.assertEqual(self.customer_one.name, "Updated Alpha Stores")

    def test_admin_can_update_customer(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"{self.list_url}{self.customer_one.pk}/",
            {"name": "Admin Updated Customer"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.customer_one.refresh_from_db()
        self.assertEqual(
        self.customer_one.name,
        "Admin Updated Customer",
        )

    def test_sales_staff_cannot_create_customer(self):
        sales_group, _ = Group.objects.get_or_create(name=SALES_GROUP)
        self.regular_user.groups.add(sales_group)
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            self.list_url,
            {
                "name": "Sales Created Customer",
                "email": "sales-created@example.com",
                "phone": "9876543212",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            Customer.objects.filter(
                name="Sales Created Customer"
            ).exists()
        )

    def test_warehouse_staff_cannot_create_customer(self):
        warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )
        self.regular_user.groups.add(warehouse_group)
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            self.list_url,
            {
                "name": "Warehouse Created Customer",
                "email": "warehouse-created@example.com",
                "phone": "9876543213",
                "is_active": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            Customer.objects.filter(
                name="Warehouse Created Customer"
            ).exists()
        )

    def test_warehouse_staff_cannot_update_customer(self):
        warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )
        self.regular_user.groups.add(warehouse_group)
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.patch(
            f"{self.list_url}{self.customer_one.pk}/",
            {"name": "Unauthorized Warehouse Update"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.customer_one.refresh_from_db()
        self.assertEqual(self.customer_one.name, "Alpha Stores")

    def test_anonymous_user_cannot_retrieve_customer(self):
        response = self.client.get(
            f"{self.list_url}{self.customer_one.pk}/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
