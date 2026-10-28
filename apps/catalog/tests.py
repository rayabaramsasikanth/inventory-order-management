from django.core.exceptions import ValidationError
from apps.catalog.services import (
    record_stock_movement,
    reserve_stock,
    release_reserved_stock,
)

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Supplier, Product, Warehouse, Inventory, StockMovement
from apps.core.models import User
from apps.core.permissions import ADMIN_GROUP, WAREHOUSE_GROUP


User = get_user_model()


class SupplierAPITests(APITestCase):
    def setUp(self):
        # Create an administrator and a warehouse staff member.
        self.admin = User.objects.create_user(
            username="supplieradmin",
            password="StrongPass!927",
        )
        self.admin_group, _ = Group.objects.get_or_create(
            name=ADMIN_GROUP
        )
        self.admin.groups.add(self.admin_group)

        self.warehouse_user = User.objects.create_user(
            username="warehouseuser",
            password="StrongPass!927",
        )
        self.warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )
        self.warehouse_user.groups.add(self.warehouse_group)

        # Use the real API endpoint paths.
        self.list_url = "/api/catalog/suppliers/"

    def supplier_data(self):
        # Return valid data for creating a supplier.
        return {
            "name": "ABC Electronics",
            "email": "abc@example.com",
            "phone": "+91 9876543210",
            "address": "Hyderabad, India",
        }

    def test_admin_can_create_supplier(self):
        # Authenticate as an administrator.
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.list_url,
            self.supplier_data(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertTrue(
            Supplier.objects.filter(email="abc@example.com").exists()
        )

    def test_warehouse_staff_can_list_suppliers(self):
        # Create a supplier to appear in the list.
        Supplier.objects.create(
            name="ABC Electronics",
            email="abc@example.com",
        )

        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_warehouse_staff_cannot_create_supplier(self):
        # Only administrators can create suppliers.
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.post(
            self.list_url,
            self.supplier_data(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(Supplier.objects.count(), 0)

    def test_anonymous_user_cannot_list_suppliers(self):
        # Authentication is required for the supplier API.
        response = self.client.get(self.list_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_admin_can_update_supplier(self):
        # Create an existing supplier.
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
        # Administrators can delete supplier records.
        supplier = Supplier.objects.create(
            name="ABC Electronics",
            email="abc@example.com",
        )
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(
            f"{self.list_url}{supplier.pk}/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(
            Supplier.objects.filter(pk=supplier.pk).exists()
        )


class ProductAPITests(APITestCase):
    def setUp(self):
        # Create an administrator and assign the Admin role.
        self.admin = User.objects.create_user(
            username="productadmin",
            password="StrongPass!927",
        )
        admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        self.admin.groups.add(admin_group)

        # Create a warehouse staff user.
        self.warehouse_user = User.objects.create_user(
            username="productwarehouse",
            password="StrongPass!927",
        )
        warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP
        )
        self.warehouse_user.groups.add(warehouse_group)

        # Every product must reference an existing supplier.
        self.supplier = Supplier.objects.create(
            name="ABC Electronics",
            email="abc@example.com",
        )

        self.list_url = "/api/catalog/products/"

    def product_data(self, **overrides):
        # Return valid product data; individual tests can override fields.
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
        # Create an administrator and assign the Admin group.
        self.admin = User.objects.create_user(
            username="warehouseadmin",
            password="StrongPass!927",
        )
        admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
        self.admin.groups.add(admin_group)

        # Create a warehouse staff user.
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
        # Create a user responsible for recording stock changes.
        self.user = User.objects.create_user(
            username="stock_admin",
            password="TestPass123!",
        )

        self.supplier = Supplier.objects.create(
            name="Test Supplier",
            email="supplier@example.com",
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
            email="service@example.com",
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
        # Reserving stock must not reduce the physical quantity.
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
        # Only two units are available: 10 physical minus 8 reserved.
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
        # Releasing a reservation makes stock available without changing
        # the physical quantity in the warehouse.
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


class StockMovementAPITests(APITestCase):
    def setUp(self):
        from django.contrib.auth.models import Group
        from rest_framework_simplejwt.tokens import RefreshToken

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
            email="api-supplier@example.com",
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

        self.assertEqual(response.status_code, 201)

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 150)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.assertEqual(
            StockMovement.objects.get().created_by,
            self.admin,
        )

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

        self.assertEqual(response.status_code, 201)

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

        self.assertEqual(response.status_code, 403)

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

        self.assertEqual(response.status_code, 400)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 100)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_anonymous_user_cannot_list_movements(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)
