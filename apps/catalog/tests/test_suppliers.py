
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Supplier
from apps.core.permissions import (
    ADMIN_GROUP,
    SALES_GROUP,
    WAREHOUSE_GROUP,
)

User = get_user_model()


class SupplierAPITests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="supplieradmin",
            password="StrongPass!927",
        )
        self.admin_group, _ = Group.objects.get_or_create(
            name=ADMIN_GROUP,
        )
        self.admin.groups.add(self.admin_group)

        self.warehouse_user = User.objects.create_user(
            username="warehouseuser",
            password="StrongPass!927",
        )
        self.warehouse_group, _ = Group.objects.get_or_create(
            name=WAREHOUSE_GROUP,
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

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )
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
        self.assertEqual(len(response.data["results"]), 1)

    def test_warehouse_staff_cannot_create_supplier(self):
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

    def test_sales_staff_cannot_create_supplier(self):
        sales_user = User.objects.create_user(
            username="salessupplier",
            password="StrongPass!927",
        )
        sales_group, _ = Group.objects.get_or_create(
            name=SALES_GROUP,
        )
        sales_user.groups.add(sales_group)
        self.client.force_authenticate(user=sales_user)

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

    def test_warehouse_staff_cannot_retrieve_supplier(self):
        supplier = Supplier.objects.create(
            name="ABC Electronics",
            email="abc@example.com",
        )
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.get(
            f"{self.list_url}{supplier.pk}/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_warehouse_staff_cannot_update_supplier(self):
        supplier = Supplier.objects.create(
            name="ABC Electronics",
            email="abc@example.com",
        )
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.patch(
            f"{self.list_url}{supplier.pk}/",
            {"phone": "+91 9999999999"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        supplier.refresh_from_db()
        self.assertNotEqual(supplier.phone, "+91 9999999999")

    def test_warehouse_staff_cannot_delete_supplier(self):
        supplier = Supplier.objects.create(
            name="ABC Electronics",
            email="abc@example.com",
        )
        self.client.force_authenticate(user=self.warehouse_user)

        response = self.client.delete(
            f"{self.list_url}{supplier.pk}/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertTrue(
            Supplier.objects.filter(pk=supplier.pk).exists()
        )

    def test_ordinary_user_cannot_create_supplier(self):
        ordinary_user = User.objects.create_user(
            username="ordinarysupplier",
            password="StrongPass!927",
        )
        self.client.force_authenticate(user=ordinary_user)

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

    def test_ordinary_user_cannot_access_supplier_detail_actions(self):
        ordinary_user = User.objects.create_user(
            username="ordinarysupplierdetail",
            password="StrongPass!927",
        )
        supplier = Supplier.objects.create(
            name="ABC Electronics",
            email="abc@example.com",
        )
        self.client.force_authenticate(user=ordinary_user)

        detail_url = f"{self.list_url}{supplier.pk}/"

        retrieve_response = self.client.get(detail_url)
        update_response = self.client.patch(
            detail_url,
            {"phone": "+91 9999999999"},
            format="json",
        )
        delete_response = self.client.delete(detail_url)

        self.assertEqual(
            retrieve_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            update_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            delete_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        supplier.refresh_from_db()
        self.assertTrue(
            Supplier.objects.filter(pk=supplier.pk).exists()
        )
        self.assertNotEqual(supplier.phone, "+91 9999999999")
