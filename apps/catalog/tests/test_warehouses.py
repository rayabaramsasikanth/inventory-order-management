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


class WarehouseAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="warehouseadmin",
            password="StrongPass!927",
        )
        admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        self.admin.groups.add(admin_group)

        self.warehouse_user = User.objects.create_user(
            username="warehouseoperator",
            password="StrongPass!927",
        )
        warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )
        self.warehouse_user.groups.add(warehouse_group)

        self.list_url = "/api/catalog/warehouses/"

    def warehouse_data(self):
        return {
            "name": "Hyderabad Main Warehouse",
            "code": "hyd-001",
            "address": "Hyderabad, India",
        }

    def test_admin_can_create_warehouse(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.list_url,
            self.warehouse_data(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Warehouse.objects.filter(code="HYD-001").exists()
        )

    def test_warehouse_staff_can_list_warehouses(self):
        Warehouse.objects.create(
            name="Hyderabad Main Warehouse",
            code="HYD-001",
        )
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_warehouse_staff_cannot_create_warehouse(self):
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.post(
            self.list_url,
            self.warehouse_data(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Warehouse.objects.count(), 0)

    def test_anonymous_user_cannot_list_warehouses(self):
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_admin_can_update_warehouse(self):
        warehouse = Warehouse.objects.create(
            name="Hyderabad Main Warehouse",
            code="HYD-001",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"{self.list_url}{warehouse.pk}/",
            {"name": "Hyderabad Central Warehouse"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        warehouse.refresh_from_db()
        self.assertEqual(warehouse.name, "Hyderabad Central Warehouse")

    def test_admin_can_delete_warehouse(self):
        warehouse = Warehouse.objects.create(
            name="Hyderabad Main Warehouse",
            code="HYD-001",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(
            f"{self.list_url}{warehouse.pk}/"
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            Warehouse.objects.filter(pk=warehouse.pk).exists()
        )
