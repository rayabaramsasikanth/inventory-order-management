from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Inventory, Order, Product, StockMovement, Supplier, Warehouse
from apps.catalog.services import create_order, update_order_status
from apps.catalog.tasks import expire_pending_orders
from apps.core.permissions import ADMIN_GROUP

User = get_user_model()


class StockTransferAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username="transfer-admin", password="StrongPass!927"
        )
        group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        self.admin.groups.add(group)
        self.supplier = Supplier.objects.create(
            name="Transfer Supplier", email="transfer-supplier@example.com"
        )
        self.product = Product.objects.create(
            sku="TRANSFER-001", name="Transfer Product", supplier=self.supplier,
            cost_price="10.00", selling_price="15.00",
        )
        self.source = Warehouse.objects.create(name="Source", code="SRC")
        self.destination = Warehouse.objects.create(name="Destination", code="DST")
        Inventory.objects.create(product=self.product, warehouse=self.source, quantity=20)
        self.client.force_authenticate(user=self.admin)

    def test_transfer_creates_paired_ledger_entries_and_updates_stock(self):
        payload = {
            "product": self.product.pk,
            "source_warehouse": self.source.pk,
            "destination_warehouse": self.destination.pk,
            "quantity": 5,
            "reason": "Rebalance stock",
        }
        response = self.client.post(
            "/api/catalog/stock-transfers/", payload, format="json",
            HTTP_IDEMPOTENCY_KEY="transfer-001",
        )
        replay = self.client.post(
            "/api/catalog/stock-transfers/", payload, format="json",
            HTTP_IDEMPOTENCY_KEY="transfer-001",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(replay.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data, replay.data)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(StockMovement.objects.count(), 2)
        source_stock = Inventory.objects.get(product=self.product, warehouse=self.source)
        destination_stock = Inventory.objects.get(product=self.product, warehouse=self.destination)
        self.assertEqual(source_stock.quantity, 15)
        self.assertEqual(destination_stock.quantity, 5)


class ReservationExpiryTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="expiry-user", password="StrongPass!927"
        )
        supplier = Supplier.objects.create(
            name="Expiry Supplier", email="expiry@example.com"
        )
        self.product = Product.objects.create(
            sku="EXPIRY-001", name="Expiry Product", supplier=supplier,
            cost_price="1.00", selling_price="2.00",
        )
        self.warehouse = Warehouse.objects.create(name="Expiry Warehouse", code="EXP")
        self.inventory = Inventory.objects.create(
            product=self.product, warehouse=self.warehouse, quantity=10
        )

    def test_expiry_task_cancels_stale_pending_order_and_releases_stock(self):
        order = create_order(
            order_number="EXPIRY-ORDER-001", warehouse=self.warehouse,
            created_by=self.user, items=[{"product": self.product, "quantity": 3}],
        )
        order.expires_at = timezone.now() - timedelta(minutes=1)
        order.save(update_fields=["expires_at"])

        result = expire_pending_orders.run()

        order.refresh_from_db()
        self.inventory.refresh_from_db()
        self.assertEqual(result["expired"], 1)
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.inventory.reserved_quantity, 0)

    def test_confirmation_disables_pending_reservation_expiry(self):
        order = create_order(
            order_number="EXPIRY-ORDER-002", warehouse=self.warehouse,
            created_by=self.user, items=[{"product": self.product, "quantity": 2}],
        )
        self.assertIsNotNone(order.expires_at)
        order = update_order_status(
            order_id=order.pk, new_status=Order.Status.CONFIRMED, updated_by=self.user
        )
        self.assertIsNone(order.expires_at)
