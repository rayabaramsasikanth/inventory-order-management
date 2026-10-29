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


class ProductAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="productadmin",
            password="StrongPass!927",
        )
        admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        self.admin.groups.add(admin_group)

        self.warehouse_user = User.objects.create_user(
            username="productwarehouse",
            password="StrongPass!927",
        )
        warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )
        self.warehouse_user.groups.add(warehouse_group)

        self.supplier = Supplier.objects.create(
            name="ABC Electronics",
            email="product-supplier@example.com",
        )
        self.list_url = "/api/catalog/products/"

    def product_data(self, **overrides):
        data = {
            "sku": "KB-LOG-001",
            "name": "Logitech Keyboard",
            "description": "Wireless keyboard",
            "supplier": self.supplier.pk,
            "cost_price": "1200.00",
            "selling_price": "1599.00",
        }
        data.update(overrides)
        return data

    def test_admin_can_create_product(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.list_url,
            self.product_data(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Product.objects.filter(sku="KB-LOG-001").exists()
        )
        self.assertEqual(response.data["supplier_name"], "ABC Electronics")

    def test_warehouse_staff_can_list_products(self):
        Product.objects.create(
            sku="KB-LOG-001",
            name="Logitech Keyboard",
            supplier=self.supplier,
            cost_price="1200.00",
            selling_price="1599.00",
        )
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.get(self.list_url)
        print("STATUS:", response.status_code)
        print("DATA:", response.data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_warehouse_staff_cannot_create_product(self):
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.post(
            self.list_url,
            self.product_data(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Product.objects.count(), 0)

    def test_duplicate_sku_is_rejected(self):
        Product.objects.create(
            sku="KB-LOG-001",
            name="Existing Keyboard",
            supplier=self.supplier,
            cost_price="1000.00",
            selling_price="1400.00",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.list_url,
            self.product_data(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Product.objects.count(), 1)

    def test_negative_price_is_rejected(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.list_url,
            self.product_data(cost_price="-1.00"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Product.objects.count(), 0)

    def test_admin_can_update_product(self):
        product = Product.objects.create(
            sku="KB-LOG-001",
            name="Logitech Keyboard",
            supplier=self.supplier,
            cost_price="1200.00",
            selling_price="1599.00",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"{self.list_url}{product.pk}/",
            {"selling_price": "1699.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        self.assertEqual(str(product.selling_price), "1699.00")


    def test_product_search_by_name(self):
        Product.objects.create(
            sku="SEARCH-001",
            name="Gaming Mouse",
            supplier=self.supplier,
            cost_price="500.00",
            selling_price="750.00",
        )
        Product.objects.create(
            sku="SEARCH-002",
            name="Office Chair",
            supplier=self.supplier,
            cost_price="2000.00",
            selling_price="3000.00",
        )

        self.client.force_authenticate(user=self.warehouse_user)
        response = self.client.get(
            self.list_url,
            {"search": "Gaming Mouse"},
        )
        print("STATUS:", response.status_code)
        print("DATA:", response.data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["name"],
            "Gaming Mouse",
        )

    def test_product_filter_by_active_status(self):
        Product.objects.create(
            sku="FILTER-001",
            name="Active Product",
            supplier=self.supplier,
            cost_price="100.00",
            selling_price="150.00",
            is_active=True,
        )
        Product.objects.create(
            sku="FILTER-002",
            name="Inactive Product",
            supplier=self.supplier,
            cost_price="100.00",
            selling_price="150.00",
            is_active=False,
        )

        self.client.force_authenticate(user=self.warehouse_user)
        response = self.client.get(
            self.list_url,
            {"is_active": "false"},
        )
        print("STATUS:", response.status_code)
        print("DATA:", response.data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["name"],
            "Inactive Product",
        )

    def test_product_ordering_by_selling_price(self):
        Product.objects.create(
            sku="ORDER-001",
            name="Expensive Product",
            supplier=self.supplier,
            cost_price="500.00",
            selling_price="900.00",
        )
        Product.objects.create(
            sku="ORDER-002",
            name="Cheap Product",
            supplier=self.supplier,
            cost_price="100.00",
            selling_price="200.00",
        )

        self.client.force_authenticate(user=self.warehouse_user)
        response = self.client.get(
            self.list_url,
            {"ordering": "selling_price"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["results"][0]["name"],
            "Cheap Product",
        )
        self.assertEqual(
            response.data["results"][1]["name"],
            "Expensive Product",
        )

    def test_product_pagination(self):
        for number in range(3):
            Product.objects.create(
                sku=f"PAGE-{number:03}",
                name=f"Pagination Product {number}",
                supplier=self.supplier,
                cost_price="100.00",
                selling_price="150.00",
            )

        self.client.force_authenticate(user=self.warehouse_user)
        response = self.client.get(
            self.list_url,
            {"page_size": 2},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertIsNotNone(response.data["next"])
