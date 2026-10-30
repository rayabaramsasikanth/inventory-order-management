"""PostgreSQL-only row-locking regression tests (skipped on SQLite)."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from apps.catalog.models import Inventory, Product, StockMovement, Supplier, Warehouse
from apps.catalog.services import record_stock_movement

User = get_user_model()


@skipUnless(
    connection.features.has_select_for_update,
    "Requires a database with SELECT FOR UPDATE (run after PostgreSQL is configured).",
)
class PostgreSQLStockConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = User.objects.create_user(username="pg-lock-user", password="StrongPass!927")
        supplier = Supplier.objects.create(name="PG Lock Supplier", email="pg-lock@example.com")
        self.product = Product.objects.create(
            sku="PG-LOCK-001", name="Lock Test Product", supplier=supplier,
            cost_price="1.00", selling_price="2.00",
        )
        self.warehouse = Warehouse.objects.create(name="Lock Warehouse", code="LOCK-WH")
        self.inventory = Inventory.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=10,
        )

    def test_concurrent_issues_cannot_overdraw_stock(self):
        barrier = Barrier(2)

        def issue_seven_units():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                record_stock_movement(
                    product=Product.objects.get(pk=self.product.pk),
                    warehouse=Warehouse.objects.get(pk=self.warehouse.pk),
                    quantity=-7,
                    movement_type=StockMovement.MovementType.ISSUE,
                    created_by=User.objects.get(pk=self.user.pk),
                    reason="Concurrent issue test",
                )
                return "success"
            except Exception as exc:  # one transaction must fail validation
                return type(exc).__name__
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: issue_seven_units(), range(2)))

        self.inventory.refresh_from_db()
        self.assertEqual(outcomes.count("success"), 1)
        self.assertEqual(self.inventory.quantity, 3)
        self.assertEqual(StockMovement.objects.count(), 1)
