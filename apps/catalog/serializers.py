
from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import (
    Inventory,
    Product,
    StockMovement,
    Supplier,
    Warehouse,
)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id", "name", "email", "phone", "address", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProductSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "description", "supplier", "supplier_name",
            "cost_price", "selling_price", "is_active", "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_sku(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("SKU cannot be empty.")

        return value

    def validate(self, attrs):
        cost_price = attrs.get(
            "cost_price",
            getattr(self.instance, "cost_price", None),
        )
        selling_price = attrs.get(
            "selling_price",
            getattr(self.instance, "selling_price", None),
        )

        if cost_price is not None and cost_price < Decimal("0.00"):
            raise serializers.ValidationError({
                "cost_price": "Cost price cannot be negative."
            })

        if selling_price is not None and selling_price < Decimal("0.00"):
            raise serializers.ValidationError({
                "selling_price": "Selling price cannot be negative."
            })

        return attrs


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            "id", "name", "code", "address", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_code(self, value):
        value = value.strip().upper()

        if not value:
            raise serializers.ValidationError(
                "Warehouse code cannot be empty."
            )

        return value



class InventorySerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(
        source="product.sku",
        read_only=True,
    )
    warehouse_code = serializers.CharField(
        source="warehouse.code",
        read_only=True,
    )
    available_quantity = serializers.SerializerMethodField()
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = Inventory
        fields = [
            "id",
            "product",
            "product_sku",
            "warehouse",
            "warehouse_code",
            "quantity",
            "reserved_quantity",
            "available_quantity",
            "reorder_level",
            "is_low_stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "quantity",
            "reserved_quantity",
            "created_at",
            "updated_at",
        ]

    def get_available_quantity(self, obj):
        return obj.quantity - obj.reserved_quantity

    def get_is_low_stock(self, obj):
        return self.get_available_quantity(obj) <= obj.reorder_level

    def validate(self, attrs):
        product = attrs.get(
            "product",
            getattr(self.instance, "product", None),
        )
        warehouse = attrs.get(
            "warehouse",
            getattr(self.instance, "warehouse", None),
        )

        if product and not product.is_active:
            raise serializers.ValidationError({
                "product": "Cannot add stock for an inactive product."
            })

        if warehouse and not warehouse.is_active:
            raise serializers.ValidationError({
                "warehouse": "Cannot add stock to an inactive warehouse."
            })

        return attrs


class StockMovementSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )

    class Meta:
        model = StockMovement
        fields = [
            "id", "product", "product_sku", "warehouse", "warehouse_code",
            "quantity", "movement_type", "reason", "created_by",
            "created_by_username", "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

    def validate(self, attrs):
        quantity = attrs.get("quantity")
        movement_type = attrs.get("movement_type")
        product = attrs.get("product")
        warehouse = attrs.get("warehouse")

        if quantity == 0:
            raise serializers.ValidationError({
                "quantity": "Quantity cannot be zero."
            })

        if movement_type in {
            StockMovement.MovementType.TRANSFER_IN,
            StockMovement.MovementType.TRANSFER_OUT,
        }:
            raise serializers.ValidationError({
                "movement_type": (
                    "Transfers must be performed through the warehouse "
                    "transfer service."
                )
            })

        if product and not product.is_active:
            raise serializers.ValidationError({
                "product": "Cannot create a movement for an inactive product."
            })

        if warehouse and not warehouse.is_active:
            raise serializers.ValidationError({
                "warehouse": "Cannot create a movement in an inactive warehouse."
            })

        return attrs
