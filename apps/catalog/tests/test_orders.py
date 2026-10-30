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


class OrderServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="order_service_user",
            password="StrongPass!927",
        )
        self.supplier = Supplier.objects.create(
            name="Order Test Supplier",
            email="order-test@example.com",
        )
        self.product = Product.objects.create(
            sku="ORDER-001",
            name="Order Test Product",
            supplier=self.supplier,
            cost_price="50.00",
            selling_price="75.00",
        )
        self.second_product = Product.objects.create(
            sku="ORDER-002",
            name="Second Order Product",
            supplier=self.supplier,
            cost_price="100.00",
            selling_price="150.00",
        )
        self.warehouse = Warehouse.objects.create(
            name="Order Test Warehouse",
            code="ORDER-WH",
        )

        # Both products have stock available for order tests.
        self.inventory = Inventory.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            quantity=100,
        )
        self.second_inventory = Inventory.objects.create(
            product=self.second_product,
            warehouse=self.warehouse,
            quantity=100,
        )

    def test_create_order_with_multiple_items(self):
        order = create_order(
            order_number="ORD-TEST-001",
            warehouse=self.warehouse,
            created_by=self.user,
            items=[
                {"product": self.product, "quantity": 2},
                {"product": self.second_product, "quantity": 3},
            ],
        )

        self.assertEqual(order.created_by, self.user)
        self.assertEqual(order.warehouse, self.warehouse)
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(order.total_amount, Decimal("600.00"))

        self.inventory.refresh_from_db()
        self.second_inventory.refresh_from_db()

        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(self.inventory.reserved_quantity, 2)
        self.assertEqual(self.second_inventory.quantity, 100)
        self.assertEqual(self.second_inventory.reserved_quantity, 3)

    def test_order_captures_selling_price(self):
        order = create_order(
            order_number="ORD-TEST-002",
            warehouse=self.warehouse,
            created_by=self.user,
            items=[{"product": self.product, "quantity": 2}],
        )

        item = order.items.get()
        self.assertEqual(item.unit_price, Decimal("75.00"))

        self.product.selling_price = "90.00"
        self.product.save()

        item.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal("75.00"))
        self.assertEqual(order.total_amount, Decimal("150.00"))

    def test_empty_order_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_order(
                order_number="ORD-TEST-003",
                warehouse=self.warehouse,
                created_by=self.user,
                items=[],
            )

        self.assertEqual(Order.objects.count(), 0)

    def test_zero_quantity_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_order(
                order_number="ORD-TEST-004",
                warehouse=self.warehouse,
                created_by=self.user,
                items=[{"product": self.product, "quantity": 0}],
            )

        self.assertEqual(Order.objects.count(), 0)

    def test_negative_quantity_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_order(
                order_number="ORD-TEST-005",
                warehouse=self.warehouse,
                created_by=self.user,
                items=[{"product": self.product, "quantity": -2}],
            )

        self.assertEqual(Order.objects.count(), 0)

    def test_duplicate_product_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_order(
                order_number="ORD-TEST-006",
                warehouse=self.warehouse,
                created_by=self.user,
                items=[
                    {"product": self.product, "quantity": 1},
                    {"product": self.product, "quantity": 2},
                ],
            )

        self.assertEqual(Order.objects.count(), 0)

    def test_inactive_product_is_rejected(self):
        self.product.is_active = False
        self.product.save()

        with self.assertRaises(ValidationError):
            create_order(
                order_number="ORD-TEST-007",
                warehouse=self.warehouse,
                created_by=self.user,
                items=[{"product": self.product, "quantity": 1}],
            )

        self.assertEqual(Order.objects.count(), 0)

    def test_inactive_warehouse_is_rejected(self):
        self.warehouse.is_active = False
        self.warehouse.save()

        with self.assertRaises(ValidationError):
            create_order(
                order_number="ORD-TEST-008",
                warehouse=self.warehouse,
                created_by=self.user,
                items=[{"product": self.product, "quantity": 1}],
            )

        self.assertEqual(Order.objects.count(), 0)

    def test_duplicate_order_number_is_rejected(self):
        create_order(
            order_number="ORD-DUPLICATE",
            warehouse=self.warehouse,
            created_by=self.user,
            items=[{"product": self.product, "quantity": 1}],
        )

        with self.assertRaises(Exception):
            create_order(
                order_number="ORD-DUPLICATE",
                warehouse=self.warehouse,
                created_by=self.user,
                items=[{"product": self.second_product, "quantity": 1}],
            )

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)

    def test_insufficient_stock_rejects_order(self):
        with self.assertRaises(ValidationError):
            create_order(
                order_number="ORD-INSUFFICIENT",
                warehouse=self.warehouse,
                created_by=self.user,
                items=[{"product": self.product, "quantity": 101}],
            )

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.reserved_quantity, 0)

    def test_failed_later_item_rolls_back_earlier_reservation(self):
        self.second_inventory.quantity = 1
        self.second_inventory.save(update_fields=["quantity"])

        with self.assertRaises(ValidationError):
            create_order(
                order_number="ORD-ROLLBACK",
                warehouse=self.warehouse,
                created_by=self.user,
                items=[
                    {"product": self.product, "quantity": 5},
                    {"product": self.second_product, "quantity": 2},
                ],
            )

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

        self.inventory.refresh_from_db()
        self.second_inventory.refresh_from_db()

        self.assertEqual(self.inventory.reserved_quantity, 0)
        self.assertEqual(self.second_inventory.reserved_quantity, 0)


    def test_cancelling_order_releases_reserved_stock(self):
        order = create_order(
            order_number="ORD-CANCEL-TEST",
            warehouse=self.warehouse,
            items=[
                {"product": self.product, "quantity": 2},
            ],
            created_by=self.user,
        )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.reserved_quantity, 2)

        cancel_order(order_id=order.pk)

        order.refresh_from_db()
        self.inventory.refresh_from_db()

        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(self.inventory.reserved_quantity, 0)

    def test_fulfilling_order_deducts_stock_and_records_movement(self):
        order = create_order(
            order_number="ORD-FULFIL-TEST",
            warehouse=self.warehouse,
            items=[
                {"product": self.product, "quantity": 2},
            ],
            created_by=self.user,
        )

        order.status = Order.Status.PROCESSING
        order.save(update_fields=["status"])

        fulfil_order(
            order_id=order.pk,
            fulfilled_by=self.user,
        )

        order.refresh_from_db()
        self.inventory.refresh_from_db()

        self.assertEqual(order.status, Order.Status.FULFILLED)
        self.assertEqual(self.inventory.quantity, 98)
        self.assertEqual(self.inventory.reserved_quantity, 0)

        movement = StockMovement.objects.get(
            product=self.product,
            warehouse=self.warehouse,
            reason=f"Order fulfilment: {order.order_number}",
        )
        self.assertEqual(movement.quantity, -2)
        self.assertEqual(
            movement.movement_type,
            StockMovement.MovementType.ISSUE,
        )

    def test_cannot_cancel_processing_order(self):
        order = create_order(
            order_number="ORD-INVALID-CANCEL",
            warehouse=self.warehouse,
            items=[
                {"product": self.product, "quantity": 2},
            ],
            created_by=self.user,
        )

        order.status = Order.Status.PROCESSING
        order.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            cancel_order(order_id=order.pk)

        order.refresh_from_db()
        self.inventory.refresh_from_db()

        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(self.inventory.reserved_quantity, 2)


    def test_pending_order_can_be_confirmed(self):
        order = create_order(
            order_number="ORD-STATUS-001",
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 2}],
            created_by=self.user,
        )

        update_order_status(
            order_id=order.pk,
            new_status=Order.Status.CONFIRMED,
            updated_by=self.user,
        )

        order.refresh_from_db()
        self.inventory.refresh_from_db()

        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(self.inventory.reserved_quantity, 2)

    def test_confirmed_order_can_enter_processing(self):
        order = create_order(
            order_number="ORD-STATUS-002",
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 2}],
            created_by=self.user,
        )
        order.status = Order.Status.CONFIRMED
        order.save(update_fields=["status"])

        update_order_status(
            order_id=order.pk,
            new_status=Order.Status.PROCESSING,
            updated_by=self.user,
        )

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PROCESSING)

    def test_status_service_rejects_invalid_transition(self):
        order = create_order(
            order_number="ORD-STATUS-003",
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 2}],
            created_by=self.user,
        )

        with self.assertRaises(ValidationError):
            update_order_status(
                order_id=order.pk,
                new_status=Order.Status.FULFILLED,
                updated_by=self.user,
            )

        order.refresh_from_db()
        self.inventory.refresh_from_db()

        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(self.inventory.reserved_quantity, 2)

    def test_status_service_cancels_and_releases_stock(self):
        order = create_order(
            order_number="ORD-STATUS-004",
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 2}],
            created_by=self.user,
        )

        update_order_status(
            order_id=order.pk,
            new_status=Order.Status.CANCELLED,
            updated_by=self.user,
        )

        order.refresh_from_db()
        self.inventory.refresh_from_db()

        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(self.inventory.reserved_quantity, 0)

    def test_status_service_fulfils_processing_order(self):
        order = create_order(
            order_number="ORD-STATUS-005",
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 2}],
            created_by=self.user,
        )
        order.status = Order.Status.PROCESSING
        order.save(update_fields=["status"])

        update_order_status(
            order_id=order.pk,
            new_status=Order.Status.FULFILLED,
            updated_by=self.user,
        )

        order.refresh_from_db()
        self.inventory.refresh_from_db()

        self.assertEqual(order.status, Order.Status.FULFILLED)
        self.assertEqual(self.inventory.quantity, 98)
        self.assertEqual(self.inventory.reserved_quantity, 0)


    def test_order_detail_api_returns_order_items_and_total(self):
        order = create_order(
            order_number="ORD-API-DETAIL",
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 2}],
            created_by=self.user,
        )

        sales_group, _ = Group.objects.get_or_create(name=SALES_GROUP)
        self.user.groups.add(sales_group)
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            reverse("order-detail", kwargs={"pk": order.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["order_number"], order.order_number)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(
            str(response.data["total_amount"]),
            "150.00",
        )

    def test_sales_staff_can_confirm_order_through_api(self):
        sales_group, _ = Group.objects.get_or_create(name=SALES_GROUP)
        self.user.groups.add(sales_group)

        order = create_order(
            order_number="ORD-API-CONFIRM",
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 2}],
            created_by=self.user,
        )

        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("order-status-update", kwargs={"pk": order.pk}),
            {"status": Order.Status.CONFIRMED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(self.inventory.reserved_quantity, 2)

    def test_order_api_rejects_invalid_status_transition(self):
        order = create_order(
            order_number="ORD-API-INVALID",
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 2}],
            created_by=self.user,
        )

        self.user.groups.add(
            Group.objects.get_or_create(name=SALES_GROUP)[0]
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("order-status-update", kwargs={"pk": order.pk}),
            {"status": Order.Status.FULFILLED},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.reserved_quantity, 2)

    def test_user_without_sales_or_admin_role_cannot_update_order(self):
        order = create_order(
            order_number="ORD-API-FORBIDDEN",
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 2}],
            created_by=self.user,
        )

        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("order-status-update", kwargs={"pk": order.pk}),
            {"status": Order.Status.CONFIRMED},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)


    def test_create_order_with_customer(self):
        customer = Customer.objects.create(
            name="Order Customer",
            email="ordercustomer@example.com",
            is_active=True,
        )

        order = create_order(
            order_number="ORD-CUSTOMER-001",
            warehouse=self.warehouse,
            created_by=self.user,
            customer=customer,
            items=[
                {"product": self.product, "quantity": 2},
            ],
        )

        self.assertEqual(order.customer, customer)
        self.assertEqual(order.customer.name, "Order Customer")

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.reserved_quantity, 2)

    def test_multiple_orders_can_belong_to_same_customer(self):
        customer = Customer.objects.create(
            name="Repeat Customer",
            email="repeat@example.com",
            is_active=True,
        )

        first_order = create_order(
            order_number="ORD-CUSTOMER-002",
            warehouse=self.warehouse,
            created_by=self.user,
            customer=customer,
            items=[
                {"product": self.product, "quantity": 2},
            ],
        )

        second_order = create_order(
            order_number="ORD-CUSTOMER-003",
            warehouse=self.warehouse,
            created_by=self.user,
            customer=customer,
            items=[
                {"product": self.second_product, "quantity": 3},
            ],
        )

        self.assertEqual(first_order.customer, customer)
        self.assertEqual(second_order.customer, customer)
        self.assertEqual(customer.orders.count(), 2)

    def test_inactive_customer_cannot_place_order(self):
        customer = Customer.objects.create(
            name="Inactive Customer",
            email="inactive@example.com",
            is_active=False,
        )

        with self.assertRaises(ValidationError):
            create_order(
                order_number="ORD-CUSTOMER-004",
                warehouse=self.warehouse,
                created_by=self.user,
                customer=customer,
                items=[
                    {"product": self.product, "quantity": 1},
                ],
            )

        self.assertFalse(
            Order.objects.filter(
                order_number="ORD-CUSTOMER-004"
            ).exists()
        )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.reserved_quantity, 0)


    def test_partial_fulfilment_keeps_order_processing(self):
        order = create_order(
            order_number="ORD-PARTIAL-001",
            warehouse=self.warehouse,
            created_by=self.user,
            items=[{"product": self.product, "quantity": 10}],
        )
        order.status = Order.Status.PROCESSING
        order.save(update_fields=["status"])

        item = order.items.get()

        fulfil_order(
            order_id=order.pk,
            fulfilled_by=self.user,
            quantities={item.pk: 6},
        )

        order.refresh_from_db()
        item.refresh_from_db()
        self.inventory.refresh_from_db()

        self.assertEqual(item.quantity, 10)
        self.assertEqual(item.fulfilled_quantity, 6)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(self.inventory.quantity, 94)
        self.assertEqual(self.inventory.reserved_quantity, 4)

    def test_remaining_quantity_completes_order(self):
        order = create_order(
            order_number="ORD-PARTIAL-002",
            warehouse=self.warehouse,
            created_by=self.user,
            items=[{"product": self.product, "quantity": 10}],
        )
        order.status = Order.Status.PROCESSING
        order.save(update_fields=["status"])

        item = order.items.get()

        fulfil_order(
            order_id=order.pk,
            fulfilled_by=self.user,
            quantities={item.pk: 6},
        )
        fulfil_order(
            order_id=order.pk,
            fulfilled_by=self.user,
            quantities={item.pk: 4},
        )

        order.refresh_from_db()
        item.refresh_from_db()
        self.inventory.refresh_from_db()

        self.assertEqual(item.fulfilled_quantity, 10)
        self.assertEqual(order.status, Order.Status.FULFILLED)
        self.assertEqual(self.inventory.quantity, 90)
        self.assertEqual(self.inventory.reserved_quantity, 0)

        movements = StockMovement.objects.filter(
            product=self.product,
            warehouse=self.warehouse,
            reason=f"Order fulfilment: {order.order_number}",
        )
        self.assertEqual(movements.count(), 2)
        self.assertEqual(
            sum(movement.quantity for movement in movements),
            -10,
        )

    def test_cannot_fulfil_more_than_remaining_quantity(self):
        order = create_order(
            order_number="ORD-PARTIAL-003",
            warehouse=self.warehouse,
            created_by=self.user,
            items=[{"product": self.product, "quantity": 10}],
        )
        order.status = Order.Status.PROCESSING
        order.save(update_fields=["status"])

        item = order.items.get()

        fulfil_order(
            order_id=order.pk,
            fulfilled_by=self.user,
            quantities={item.pk: 6},
        )

        with self.assertRaises(ValidationError):
            fulfil_order(
                order_id=order.pk,
                fulfilled_by=self.user,
                quantities={item.pk: 5},
            )

        order.refresh_from_db()
        item.refresh_from_db()
        self.inventory.refresh_from_db()

        self.assertEqual(item.fulfilled_quantity, 6)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(self.inventory.quantity, 94)
        self.assertEqual(self.inventory.reserved_quantity, 4)

    def test_failed_partial_fulfilment_rolls_back_all_changes(self):
        order = create_order(
            order_number="ORD-PARTIAL-004",
            warehouse=self.warehouse,
            created_by=self.user,
            items=[
                {"product": self.product, "quantity": 10},
                {"product": self.second_product, "quantity": 10},
            ],
        )
        order.status = Order.Status.PROCESSING
        order.save(update_fields=["status"])

        items = {
            item.product_id: item
            for item in order.items.all()
        }

        # Simulate inconsistent inventory for the second item.
        self.second_inventory.reserved_quantity = 0
        self.second_inventory.save(update_fields=["reserved_quantity"])

        with self.assertRaises(ValidationError):
            fulfil_order(
                order_id=order.pk,
                fulfilled_by=self.user,
                quantities={
                    items[self.product.pk].pk: 4,
                    items[self.second_product.pk].pk: 4,
                },
            )

        order.refresh_from_db()
        self.inventory.refresh_from_db()
        self.second_inventory.refresh_from_db()

        for item in order.items.all():
            self.assertEqual(item.fulfilled_quantity, 0)

        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(self.inventory.reserved_quantity, 10)
        self.assertEqual(self.second_inventory.quantity, 100)
        self.assertEqual(self.second_inventory.reserved_quantity, 0)

        self.assertFalse(
            StockMovement.objects.filter(
                reason=f"Order fulfilment: {order.order_number}"
            ).exists()
        )


class OrderReadPermissionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="order_read_user",
            password="StrongPass!927",
        )

        self.sales_group, _ = Group.objects.get_or_create(
            name=SALES_GROUP,
        )
        self.admin_group, _ = Group.objects.get_or_create(
            name=ADMIN_GROUP,
        )

        supplier = Supplier.objects.create(
            name="Read Test Supplier",
            email="read-test@example.com",
        )
        product = Product.objects.create(
            sku="READ-001",
            name="Read Test Product",
            supplier=supplier,
            cost_price="50.00",
            selling_price="75.00",
        )
        warehouse = Warehouse.objects.create(
            name="Read Test Warehouse",
            code="READ-WH",
        )
        Inventory.objects.create(
            product=product,
            warehouse=warehouse,
            quantity=20,
        )

        self.order = create_order(
            order_number="ORD-READ-001",
            warehouse=warehouse,
            created_by=self.user,
            items=[{"product": product, "quantity": 2}],
        )

    def test_anonymous_user_cannot_access_order_endpoints(self):
        self.client.force_authenticate(user=None)

        order_item = self.order.items.first()
        order_url = reverse(
            "order-detail",
            kwargs={"pk": self.order.pk},
        )

        requests = [
            self.client.get(reverse("order-list-create")),
            self.client.post(
                reverse("order-list-create"),
                {},
                format="json",
            ),
            self.client.get(order_url),
            self.client.patch(
                reverse(
                    "order-status-update",
                    kwargs={"pk": self.order.pk},
                ),
                {"status": Order.Status.CONFIRMED},
                format="json",
            ),
            self.client.post(
                reverse(
                    "order-fulfilment",
                    kwargs={"pk": self.order.pk},
                ),
                {
                    "quantities": {
                        str(order_item.pk): 1,
                    }
                },
                format="json",
            ),
        ]

        for response in requests:
            self.assertEqual(
                response.status_code,
                status.HTTP_401_UNAUTHORIZED,
            )

    def test_user_without_sales_or_admin_role_cannot_list_orders(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("order-list-create"))

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_user_without_sales_or_admin_role_cannot_retrieve_order(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(
            reverse("order-detail", kwargs={"pk": self.order.pk}),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_sales_staff_can_list_and_retrieve_orders(self):
        self.user.groups.add(self.sales_group)
        self.client.force_authenticate(user=self.user)

        list_response = self.client.get(reverse("order-list-create"))
        detail_response = self.client.get(
            reverse("order-detail", kwargs={"pk": self.order.pk}),
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["id"], self.order.pk)

    def test_warehouse_staff_cannot_create_order(self):
        warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP,
        )
        self.user.groups.add(warehouse_group)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            reverse("order-list-create"),
            {
                "order_number": "ORD-FORBIDDEN-CREATE",
                "warehouse": self.order.warehouse_id,
                "items": [
                    {
                        "product": self.order.items.first().product_id,
                        "quantity": 1,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertFalse(
            Order.objects.filter(
                order_number="ORD-FORBIDDEN-CREATE",
            ).exists()
        )

    def test_sales_staff_cannot_fulfil_order(self):
        self.user.groups.add(self.sales_group)
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            reverse(
                "order-fulfilment",
                kwargs={"pk": self.order.pk},
            ),
            {
                "quantities": {
                    str(self.order.items.first().pk): 1,
                }
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.order.refresh_from_db()
        self.assertEqual(
            self.order.status,
            Order.Status.PENDING,
        )


    def test_admin_can_fulfil_order(self):
        self.user.groups.add(self.admin_group)
        self.client.force_authenticate(user=self.user)

        self.order.status = Order.Status.PROCESSING
        self.order.save(update_fields=["status"])

        order_item = self.order.items.first()

        response = self.client.post(
            reverse(
                "order-fulfilment",
                kwargs={"pk": self.order.pk},
            ),
            {
                "quantities": {
                    str(order_item.pk): 1,
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        order_item.refresh_from_db()
        self.assertEqual(order_item.fulfilled_quantity, 1)

    def test_warehouse_staff_can_fulfil_order(self):
        warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP,
        )
        self.user.groups.add(warehouse_group)
        self.client.force_authenticate(user=self.user)

        self.order.status = Order.Status.PROCESSING
        self.order.save(update_fields=["status"])

        order_item = self.order.items.first()

        response = self.client.post(
            reverse(
                "order-fulfilment",
                kwargs={"pk": self.order.pk},
            ),
            {
                "quantities": {
                    str(order_item.pk): 1,
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        order_item.refresh_from_db()
        self.assertEqual(order_item.fulfilled_quantity, 1)