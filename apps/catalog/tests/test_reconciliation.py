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


class StockReconciliationServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reconciliation_test_user",
            password="Test-password-123",
        )

        self.supplier = Supplier.objects.create(
            name="Reconciliation Supplier",
            email="reconciliation@example.com",
        )

        self.product = Product.objects.create(
            sku="RECON-001",
            name="Reconciliation Product",
            supplier=self.supplier,
            cost_price="10.00",
            selling_price="15.00",
        )

        self.warehouse = Warehouse.objects.create(
            name="Reconciliation Warehouse",
            code="RECON-WH",
            address="Test address",
        )

        self.inventory = Inventory.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=100,
            reserved_quantity=20,
        )

    def test_reconciliation_records_negative_adjustment(self):
        movement = reconcile_stock(
            product=self.product,
            warehouse=self.warehouse,
            physical_count=96,
            created_by=self.user,
        )

        self.inventory.refresh_from_db()

        self.assertEqual(self.inventory.quantity, 96)
        self.assertEqual(self.inventory.reserved_quantity, 20)
        self.assertEqual(movement.quantity, -4)
        self.assertEqual(
            movement.movement_type,
            StockMovement.MovementType.ADJUSTMENT,
        )
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_reconciliation_records_positive_adjustment(self):
        movement = reconcile_stock(
            product=self.product,
            warehouse=self.warehouse,
            physical_count=106,
            created_by=self.user,
        )

        self.inventory.refresh_from_db()

        self.assertEqual(self.inventory.quantity, 106)
        self.assertEqual(movement.quantity, 6)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_matching_count_creates_no_movement(self):
        movement = reconcile_stock(
            product=self.product,
            warehouse=self.warehouse,
            physical_count=100,
            created_by=self.user,
        )

        self.inventory.refresh_from_db()

        self.assertIsNone(movement)
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_reconciliation_rejects_count_below_reserved_stock(self):
        with self.assertRaises(ValidationError):
            reconcile_stock(
                product=self.product,
                warehouse=self.warehouse,
                physical_count=19,
                created_by=self.user,
            )

        self.inventory.refresh_from_db()

        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_reconciliation_rejects_negative_count(self):
        with self.assertRaises(ValidationError):
            reconcile_stock(
                product=self.product,
                warehouse=self.warehouse,
                physical_count=-1,
                created_by=self.user,
            )

        self.inventory.refresh_from_db()

        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)


class StockReconciliationAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="reconciliation_api_user",
            password="Test-password-123",
        )
        warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )
        self.user.groups.add(warehouse_group)
        self.client.force_authenticate(user=self.user)

        self.supplier = Supplier.objects.create(
            name="Reconciliation API Supplier",
            email="reconciliation-api@example.com",
        )
        self.product = Product.objects.create(
            sku="RECON-API-001",
            name="Reconciliation API Product",
            supplier=self.supplier,
            cost_price="10.00",
            selling_price="15.00",
        )
        self.warehouse = Warehouse.objects.create(
            name="Reconciliation API Warehouse",
            code="RECON-API-WH",
            address="Test address",
        )
        self.inventory = Inventory.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=100,
            reserved_quantity=20,
        )
        self.url = "/api/catalog/inventory/reconcile/"

    def test_reconciliation_api_creates_adjustment(self):
        response = self.client.post(
            self.url,
            {
                "product": self.product.id,
                "warehouse": self.warehouse.id,
                "physical_count": 96,
                "reason": "Physical stock count",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 96)

        movement = StockMovement.objects.get()
        self.assertEqual(movement.quantity, -4)
        self.assertEqual(
            movement.movement_type,
            StockMovement.MovementType.ADJUSTMENT,
        )
        self.assertEqual(movement.created_by, self.user)

    def test_admin_can_reconcile_stock(self):
        admin = User.objects.create_user(
            username="reconciliation_admin",
            password="Test-password-123",
        )
        admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        admin.groups.add(admin_group)
        self.client.force_authenticate(user=admin)

        response = self.client.post(
            self.url,
            {
                "product": self.product.id,
                "warehouse": self.warehouse.id,
                "physical_count": 95,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 95)

        movement = StockMovement.objects.get()
        self.assertEqual(movement.quantity, -5)
        self.assertEqual(movement.created_by, admin)

    def test_sales_staff_cannot_reconcile_stock(self):
        sales_user = User.objects.create_user(
            username="reconciliation_sales",
            password="Test-password-123",
        )
        sales_group, _ = Group.objects.get_or_create(name=SALES_GROUP)
        sales_user.groups.add(sales_group)
        self.client.force_authenticate(user=sales_user)

        response = self.client.post(
            self.url,
            {
                "product": self.product.id,
                "warehouse": self.warehouse.id,
                "physical_count": 95,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_reconciliation_api_rejects_negative_count(self):
        response = self.client.post(
            self.url,
            {
                "product": self.product.id,
                "warehouse": self.warehouse.id,
                "physical_count": -1,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_reconciliation_api_rejects_count_below_reserved_stock(self):
        response = self.client.post(
            self.url,
            {
                "product": self.product.id,
                "warehouse": self.warehouse.id,
                "physical_count": 19,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_reconciliation_api_rejects_anonymous_user(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.url,
            {
                "product": self.product.id,
                "warehouse": self.warehouse.id,
                "physical_count": 96,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)
