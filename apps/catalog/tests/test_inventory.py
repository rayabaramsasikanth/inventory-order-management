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


class WarehouseTransferServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="transfer_test_user",
            password="test-password-123",
        )
        warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )
        self.user.groups.add(warehouse_group)

        self.supplier = Supplier.objects.create(
            name="Transfer Supplier",
            email="transfer-supplier@example.com",
        )
        self.product = Product.objects.create(
            sku="TRANSFER-001",
            name="Transfer Product",
            supplier=self.supplier,
            cost_price="10.00",
            selling_price="15.00",
        )
        self.source = Warehouse.objects.create(
            name="Source Warehouse",
            code="SRC",
            address="Source address",
        )
        self.destination = Warehouse.objects.create(
            name="Destination Warehouse",
            code="DST",
            address="Destination address",
        )
        self.source_inventory = Inventory.objects.create(
            product=self.product,
            warehouse=self.source,
            quantity=20,
            reserved_quantity=5,
        )
        self.destination_inventory = Inventory.objects.create(
            product=self.product,
            warehouse=self.destination,
            quantity=10,
        )

    def test_successful_transfer_updates_inventory_and_ledger(self):
        movements = transfer_stock(
            product=self.product,
            source_warehouse=self.source,
            destination_warehouse=self.destination,
            quantity=8,
            created_by=self.user,
            reason="Warehouse replenishment",
        )

        self.source_inventory.refresh_from_db()
        self.destination_inventory.refresh_from_db()

        self.assertEqual(self.source_inventory.quantity, 12)
        self.assertEqual(self.source_inventory.reserved_quantity, 5)
        self.assertEqual(self.destination_inventory.quantity, 18)

        self.assertEqual(len(movements), 2)
        self.assertEqual(StockMovement.objects.count(), 2)

        source_movement = StockMovement.objects.get(
            warehouse=self.source,
            movement_type=StockMovement.MovementType.TRANSFER_OUT,
        )
        destination_movement = StockMovement.objects.get(
            warehouse=self.destination,
            movement_type=StockMovement.MovementType.TRANSFER_IN,
        )

        self.assertEqual(source_movement.quantity, -8)
        self.assertEqual(destination_movement.quantity, 8)
        self.assertEqual(source_movement.created_by, self.user)
        self.assertEqual(destination_movement.created_by, self.user)

    def test_transfer_fails_when_available_stock_is_insufficient(self):
        with self.assertRaises(ValidationError):
            transfer_stock(
                product=self.product,
                source_warehouse=self.source,
                destination_warehouse=self.destination,
                quantity=16,
                created_by=self.user,
                reason="Test insufficient stock",
            )

        self.source_inventory.refresh_from_db()
        self.destination_inventory.refresh_from_db()

        self.assertEqual(self.source_inventory.quantity, 20)
        self.assertEqual(self.source_inventory.reserved_quantity, 5)
        self.assertEqual(self.destination_inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_transfer_rejects_same_source_and_destination(self):
        with self.assertRaises(ValidationError):
            transfer_stock(
                product=self.product,
                source_warehouse=self.source,
                destination_warehouse=self.source,
                quantity=5,
                created_by=self.user,
                reason="Invalid self-transfer",
            )

        self.source_inventory.refresh_from_db()
        self.destination_inventory.refresh_from_db()

        self.assertEqual(self.source_inventory.quantity, 20)
        self.assertEqual(self.destination_inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_transfer_rejects_inactive_product(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            transfer_stock(
                product=self.product,
                source_warehouse=self.source,
                destination_warehouse=self.destination,
                quantity=5,
                created_by=self.user,
                reason="Inactive product transfer",
            )

        self.source_inventory.refresh_from_db()
        self.destination_inventory.refresh_from_db()

        self.assertEqual(self.source_inventory.quantity, 20)
        self.assertEqual(self.destination_inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_transfer_rejects_inactive_source_warehouse(self):
        self.source.is_active = False
        self.source.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            transfer_stock(
                product=self.product,
                source_warehouse=self.source,
                destination_warehouse=self.destination,
                quantity=5,
                created_by=self.user,
              reason="Inactive source warehouse",
            )

        self.source_inventory.refresh_from_db()
        self.destination_inventory.refresh_from_db()

        self.assertEqual(self.source_inventory.quantity, 20)
        self.assertEqual(self.destination_inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.count(), 0)


    def test_transfer_rejects_inactive_destination_warehouse(self):
        self.destination.is_active = False
        self.destination.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError):
            transfer_stock(
                product=self.product,
                source_warehouse=self.source,
                destination_warehouse=self.destination,
                quantity=5,
                created_by=self.user,
                reason="Inactive destination warehouse",
            )

        self.source_inventory.refresh_from_db()
        self.destination_inventory.refresh_from_db()

        self.assertEqual(self.source_inventory.quantity, 20)
        self.assertEqual(self.destination_inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_transfer_rolls_back_if_ledger_creation_fails(self):
        with patch(
            "apps.catalog.services.StockMovement.objects.bulk_create",
            side_effect=RuntimeError("Simulated ledger failure"),
        ):
            with self.assertRaises(RuntimeError):
                transfer_stock(
                    product=self.product,
                    source_warehouse=self.source,
                    destination_warehouse=self.destination,
                    quantity=5,
                    created_by=self.user,
                    reason="Test transaction rollback",
                )

        self.source_inventory.refresh_from_db()
        self.destination_inventory.refresh_from_db()

        self.assertEqual(self.source_inventory.quantity, 20)
        self.assertEqual(self.destination_inventory.quantity, 10)
        self.assertEqual(StockMovement.objects.count(), 0)


class InventoryAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="inventory_test_user",
            password="StrongPass!927",
        )
        self.warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP,
        )
        self.user.groups.add(self.warehouse_group)

        self.supplier = Supplier.objects.create(
            name="Inventory Test Supplier",
            email="inventory-test@example.com",
        )
        self.product = Product.objects.create(
            sku="INV-TEST-001",
            name="Inventory Test Product",
            supplier=self.supplier,
            cost_price="50.00",
            selling_price="75.00",
        )
        self.warehouse = Warehouse.objects.create(
            name="Inventory Test Warehouse",
            code="INV-WH-01",
            address="Test Address",
        )
        self.inventory = Inventory.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=100,
            reserved_quantity=10,
        )
        self.client.force_authenticate(user=self.user)

    def test_create_inventory_cannot_set_quantity_directly(self):
        another_product = Product.objects.create(
            sku="INV-TEST-002",
            name="Second Inventory Test Product",
            supplier=self.supplier,
            cost_price="30.00",
            selling_price="45.00",
        )

        response = self.client.post(
            "/api/catalog/inventory/",
            {
                "product": another_product.id,
                "warehouse": self.warehouse.id,
                "quantity": 500,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )
        inventory = Inventory.objects.get(
            product=another_product,
            warehouse=self.warehouse,
        )
        self.assertEqual(inventory.quantity, 0)

    def test_update_inventory_cannot_change_quantity(self):
        response = self.client.patch(
            f"/api/catalog/inventory/{self.inventory.id}/",
            {"quantity": 500},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(self.inventory.reserved_quantity, 10)

    def test_low_stock_when_available_quantity_is_below_reorder_level(self):
        self.inventory.quantity = 20
        self.inventory.reserved_quantity = 12
        self.inventory.reorder_level = 10
        self.inventory.save()

        response = self.client.get(
            f"/api/catalog/inventory/{self.inventory.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["available_quantity"], 8)
        self.assertTrue(response.data["is_low_stock"])

    def test_low_stock_when_available_quantity_equals_reorder_level(self):
        self.inventory.quantity = 20
        self.inventory.reserved_quantity = 10
        self.inventory.reorder_level = 10
        self.inventory.save()

        response = self.client.get(
            f"/api/catalog/inventory/{self.inventory.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["available_quantity"], 10)
        self.assertTrue(response.data["is_low_stock"])

    def test_not_low_stock_when_available_quantity_exceeds_reorder_level(self):
        self.inventory.quantity = 20
        self.inventory.reserved_quantity = 9
        self.inventory.reorder_level = 10
        self.inventory.save()

        response = self.client.get(
            f"/api/catalog/inventory/{self.inventory.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["available_quantity"], 11)
        self.assertFalse(response.data["is_low_stock"])
