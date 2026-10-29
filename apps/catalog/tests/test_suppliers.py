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


class SupplierAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="supplieradmin",
            password="StrongPass!927",
        )
        self.admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        self.admin.groups.add(self.admin_group)

        self.warehouse_user = User.objects.create_user(
            username="warehouseuser",
            password="StrongPass!927",
        )
        self.warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )
        self.warehouse_user.groups.add(self.warehouse_group)

        self.list_url = "/api/catalog/suppliers/"

    def supplier_data(self):
        return {
            "name": "ABC Electronics",
            "email": "abc@example.com",
            "phone": "+91 9876543210",
            "address": "Hyderabad, India",
        }

    def test_admin_can_create_supplier(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.list_url,
            self.supplier_data(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Supplier.objects.filter(email="abc@example.com").exists()
        )

    def test_warehouse_staff_can_list_suppliers(self):
        Supplier.objects.create(
            name="ABC Electronics",
            email="abc@example.com",
        )
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_warehouse_staff_cannot_create_supplier(self):
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.post(
            self.list_url,
            self.supplier_data(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Supplier.objects.count(), 0)

    def test_anonymous_user_cannot_list_suppliers(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_admin_can_update_supplier(self):
        supplier = Supplier.objects.create(
            name="ABC Electronics",
            email="abc@example.com",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"{self.list_url}{supplier.pk}/",
            {"phone": "+91 9999999999"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        supplier.refresh_from_db()
        self.assertEqual(supplier.phone, "+91 9999999999")

    def test_admin_can_delete_supplier(self):
        supplier = Supplier.objects.create(
            name="ABC Electronics",
            email="abc@example.com",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(f"{self.list_url}{supplier.pk}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            Supplier.objects.filter(pk=supplier.pk).exists()
        )
