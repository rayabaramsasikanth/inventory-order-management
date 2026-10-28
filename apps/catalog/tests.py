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
)
from apps.catalog.services import (
    record_stock_movement,
    reserve_stock,
    release_reserved_stock,
    transfer_stock,
)

from apps.core.permissions import ADMIN_GROUP, WAREHOUSE_GROUP

from unittest.mock import patch

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
        self.assertEqual(len(response.data), 1)

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

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

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
        self.assertEqual(len(response.data), 1)

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
