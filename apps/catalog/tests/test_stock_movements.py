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


class StockMovementModelTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="stock_admin",
            password="TestPass123!",
        )
        self.supplier = Supplier.objects.create(
            name="Test Supplier",
            email="stock-model-supplier@example.com",
        )
        self.product = Product.objects.create(
            sku="TEST-001",
            name="Test Keyboard",
            supplier=self.supplier,
            cost_price="500.00",
            selling_price="750.00",
        )
        self.warehouse = Warehouse.objects.create(
            name="Hyderabad Warehouse",
            code="HYD-001",
        )

    def test_create_stock_movement(self):
        movement = StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=50,
            movement_type=StockMovement.MovementType.RECEIPT,
            reason="Supplier delivery",
            created_by=self.user,
        )

        self.assertEqual(movement.quantity, 50)
        self.assertEqual(
            movement.movement_type,
            StockMovement.MovementType.RECEIPT,
        )
        self.assertEqual(movement.created_by, self.user)

    def test_stock_movement_string_representation(self):
        movement = StockMovement.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=50,
            movement_type=StockMovement.MovementType.RECEIPT,
            created_by=self.user,
        )

        self.assertIn("TEST-001", str(movement))
        self.assertIn("HYD-001", str(movement))


class StockMovementServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="movement_admin",
            password="TestPass123!",
        )
        self.supplier = Supplier.objects.create(
            name="Service Supplier",
            email="movement-service-supplier@example.com",
        )
        self.product = Product.objects.create(
            sku="SERVICE-001",
            name="Service Keyboard",
            supplier=self.supplier,
            cost_price="500.00",
            selling_price="750.00",
        )
        self.warehouse = Warehouse.objects.create(
            name="Service Warehouse",
            code="SERVICE-001",
        )
        self.inventory = Inventory.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=100,
        )

    def test_stock_cannot_become_negative(self):
            self.inventory.quantity = 100
            self.inventory.reserved_quantity = 0
            self.inventory.save()

            with self.assertRaises(ValidationError):
                record_stock_movement(
                    product=self.product,
                    warehouse=self.warehouse,
                    quantity=-120,
                    movement_type=StockMovement.MovementType.ISSUE,
                    created_by=self.user,
                    reason="Attempted issue exceeding stock",
                )

            self.inventory.refresh_from_db()

            self.assertEqual(self.inventory.quantity, 100)
            self.assertEqual(self.inventory.reserved_quantity, 0)
            self.assertEqual(StockMovement.objects.count(), 0)


    def test_cannot_receive_stock_for_inactive_product(self):
        self.product.is_active = False
        self.product.save()

        with self.assertRaises(ValidationError):
            record_stock_movement(
                product=self.product,
                warehouse=self.warehouse,
                quantity=10,
                movement_type=StockMovement.MovementType.RECEIPT,
                created_by=self.user,
                reason="Inactive product test",
            )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_cannot_receive_stock_into_inactive_warehouse(self):
        self.warehouse.is_active = False
        self.warehouse.save()

        with self.assertRaises(ValidationError):
            record_stock_movement(
                product=self.product,
                warehouse=self.warehouse,
                quantity=10,
                movement_type=StockMovement.MovementType.RECEIPT,
                created_by=self.user,
                reason="Inactive warehouse test",
            )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_receipt_increases_stock(self):
        record_stock_movement(
            product=self.product,
            warehouse=self.warehouse,
            quantity=50,
            movement_type=StockMovement.MovementType.RECEIPT,
            created_by=self.user,
            reason="Supplier delivery",
        )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 150)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_issue_decreases_stock(self):
        record_stock_movement(
            product=self.product,
            warehouse=self.warehouse,
            quantity=-20,
            movement_type=StockMovement.MovementType.ISSUE,
            created_by=self.user,
            reason="Stock issued",
        )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 80)

    def test_zero_quantity_is_rejected(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(
                product=self.product,
                warehouse=self.warehouse,
                quantity=0,
                movement_type=StockMovement.MovementType.ADJUSTMENT,
                created_by=self.user,
            )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_stock_cannot_fall_below_reserved_quantity(self):
        self.inventory.reserved_quantity = 90
        self.inventory.save()

        with self.assertRaises(ValidationError):
            record_stock_movement(
                product=self.product,
                warehouse=self.warehouse,
                quantity=-20,
                movement_type=StockMovement.MovementType.ISSUE,
                created_by=self.user,
            )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_reserve_available_stock(self):
        self.inventory.quantity = 10
        self.inventory.reserved_quantity = 2
        self.inventory.save()

        reserve_stock(
            product=self.product,
            warehouse=self.warehouse,
            quantity=3,
        )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(self.inventory.reserved_quantity, 5)

    def test_reservation_larger_than_available_stock_is_rejected(self):
        self.inventory.quantity = 10
        self.inventory.reserved_quantity = 8
        self.inventory.save()

        with self.assertRaises(ValidationError):
            reserve_stock(
                product=self.product,
                warehouse=self.warehouse,
                quantity=3,
            )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(self.inventory.reserved_quantity, 8)

    def test_release_reserved_stock(self):
        self.inventory.quantity = 10
        self.inventory.reserved_quantity = 5
        self.inventory.save()

        release_reserved_stock(
            product=self.product,
            warehouse=self.warehouse,
            quantity=2,
        )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(self.inventory.reserved_quantity, 3)

    def test_cannot_release_more_than_reserved_stock(self):
        self.inventory.quantity = 10
        self.inventory.reserved_quantity = 2
        self.inventory.save()

        with self.assertRaises(ValidationError):
            release_reserved_stock(
                product=self.product,
                warehouse=self.warehouse,
                quantity=3,
            )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(self.inventory.reserved_quantity, 2)


    def test_inventory_update_rolls_back_if_movement_creation_fails(self):
        with patch(
            "apps.catalog.services.StockMovement.objects.create",
            side_effect=RuntimeError("Simulated database failure"),
        ):
            with self.assertRaises(RuntimeError):
                record_stock_movement(
                    product=self.product,
                    warehouse=self.warehouse,
                    quantity=10,
                    movement_type=StockMovement.MovementType.RECEIPT,
                    created_by=self.user,
                    reason="Rollback test",
                )

        self.inventory.refresh_from_db()

        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)


class StockMovementAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="movement_api_admin",
            password="TestPass123!",
        )
        self.admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        self.admin.groups.add(self.admin_group)

        self.warehouse_user = User.objects.create_user(
            username="movement_warehouse",
            password="TestPass123!",
        )
        self.warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )
        self.warehouse_user.groups.add(self.warehouse_group)

        self.supplier = Supplier.objects.create(
            name="API Supplier",
            email="stock-api-supplier@example.com",
        )
        self.product = Product.objects.create(
            sku="API-STOCK-001",
            name="API Keyboard",
            supplier=self.supplier,
            cost_price="500.00",
            selling_price="750.00",
        )
        self.warehouse = Warehouse.objects.create(
            name="API Warehouse",
            code="API-WH-001",
        )
        self.inventory = Inventory.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=100,
        )
        self.url = "/api/catalog/stock-movements/"

    def test_admin_can_record_receipt(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            {
                "product": self.product.id,
                "warehouse": self.warehouse.id,
                "quantity": 50,
                "movement_type": "RECEIPT",
                "reason": "Supplier delivery",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 150)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(StockMovement.objects.get().created_by, self.admin)

    def test_warehouse_staff_can_record_issue(self):
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.post(
            self.url,
            {
                "product": self.product.id,
                "warehouse": self.warehouse.id,
                "quantity": -20,
                "movement_type": "ISSUE",
                "reason": "Stock issued",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 80)

    def test_sales_staff_cannot_access_movements(self):
        sales_user = User.objects.create_user(
            username="movement_sales",
            password="TestPass123!",
        )
        sales_group, _ = Group.objects.get_or_create(name="Sales Staff")
        sales_user.groups.add(sales_group)

        self.client.force_authenticate(user=sales_user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_zero_quantity_is_rejected_by_api(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            {
                "product": self.product.id,
                "warehouse": self.warehouse.id,
                "quantity": 0,
                "movement_type": "ADJUSTMENT",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_anonymous_user_cannot_list_movements(self):
        response = self.client.get(self.url)
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_warehouse_staff_can_list_movements(self):
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_sales_staff_cannot_record_movement(self):
        sales_user = User.objects.create_user(
            username="movement_sales_create",
            password="TestPass123!",
        )
        sales_group, _ = Group.objects.get_or_create(name="Sales Staff")
        sales_user.groups.add(sales_group)
        self.client.force_authenticate(user=sales_user)

        response = self.client.post(
            self.url,
            {
                "product": self.product.id,
                "warehouse": self.warehouse.id,
                "quantity": 10,
                "movement_type": "RECEIPT",
                "reason": "Permission test",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_anonymous_user_cannot_record_movement(self):
        response = self.client.post(
            self.url,
            {
                "product": self.product.id,
                "warehouse": self.warehouse.id,
                "quantity": 10,
                "movement_type": "RECEIPT",
                "reason": "Permission test",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(StockMovement.objects.count(), 0)