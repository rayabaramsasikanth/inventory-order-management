
from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import (
    Customer,
    ProductCategory,
    UnitOfMeasure,
    Inventory,
    Order,
    OrderItem,
    OrderStatusHistory,
    Product,
    StockMovement,
    Supplier,
    Warehouse,
)

from drf_spectacular.utils import extend_schema_field


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "name", "slug", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ["id", "code", "name", "decimal_places", "is_active"]
        read_only_fields = ["id"]

    def validate_code(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("Unit code cannot be empty.")
        return value

    def validate_decimal_places(self, value):
        if value != 0:
            raise serializers.ValidationError(
                "This inventory ledger currently stores whole-unit quantities; use decimal_places=0."
            )
        return value


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = [
            "id", "name", "email", "phone", "address",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    unit_of_measure_code = serializers.CharField(source="unit_of_measure.code", read_only=True, allow_null=True)
    supplier_name = serializers.CharField(
        source="supplier.name", read_only=True
    )

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "description", "category", "category_name",
            "unit_of_measure", "unit_of_measure_code", "supplier", "supplier_name", "cost_price", "selling_price",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            # SKU is the stable external identifier; retire a product rather than rename its SKU.
            fields["sku"].read_only = True
        return fields

    def to_internal_value(self, data):
        if self.instance is not None and "sku" in data:
            raise serializers.ValidationError({
                "sku": "SKU is immutable. Archive this product and create a new SKU instead."
            })
        return super().to_internal_value(data)

    def validate_sku(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("SKU cannot be empty.")
        duplicates = Product.objects.filter(sku__iexact=value)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("A product with this SKU already exists.")
        return value

    def validate(self, attrs):
        category = attrs.get("category", getattr(self.instance, "category", None))
        unit = attrs.get("unit_of_measure", getattr(self.instance, "unit_of_measure", None))
        supplier = attrs.get("supplier", getattr(self.instance, "supplier", None))
        cost_price = attrs.get("cost_price", getattr(self.instance, "cost_price", None))
        selling_price = attrs.get("selling_price", getattr(self.instance, "selling_price", None))

        if category is not None and not category.is_active:
            raise serializers.ValidationError({"category": "Select an active category."})
        if unit is not None and not unit.is_active:
            raise serializers.ValidationError({"unit_of_measure": "Select an active unit of measure."})
        if supplier is not None and not supplier.is_active:
            raise serializers.ValidationError({"supplier": "Select an active supplier."})
        if cost_price is not None and cost_price < Decimal("0.00"):
            raise serializers.ValidationError({"cost_price": "Cost price cannot be negative."})
        if selling_price is not None and selling_price < Decimal("0.00"):
            raise serializers.ValidationError({"selling_price": "Selling price cannot be negative."})
        return attrs

    def create(self, validated_data):
        # Give API-created products usable defaults while keeping nullable
        # fields for legacy/imported records created outside this serializer.
        if validated_data.get("category") is None:
            category, _ = ProductCategory.objects.get_or_create(
                slug="general", defaults={"name": "General"}
            )
            if not category.is_active:
                raise serializers.ValidationError({"category": "Create or select an active category."})
            validated_data["category"] = category
        if validated_data.get("unit_of_measure") is None:
            unit, _ = UnitOfMeasure.objects.get_or_create(
                code="EA", defaults={"name": "Each", "decimal_places": 0}
            )
            if not unit.is_active:
                raise serializers.ValidationError({"unit_of_measure": "Create or select an active unit of measure."})
            validated_data["unit_of_measure"] = unit
        return super().create(validated_data)


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            "id", "name", "code", "address",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_code(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError(
                "Warehouse code cannot be empty."
            )
        return value


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id", "name", "email", "phone",
            "billing_address", "shipping_address",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "Customer name cannot be empty."
            )
        return value


class InventorySerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(
        source="product.sku", read_only=True
    )
    warehouse_code = serializers.CharField(
        source="warehouse.code", read_only=True
    )
    available_quantity = serializers.SerializerMethodField()
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = Inventory
        fields = [
            "id", "product", "product_sku", "warehouse",
            "warehouse_code", "quantity", "reserved_quantity",
            "available_quantity", "reorder_level", "is_low_stock",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "quantity", "reserved_quantity",
            "created_at", "updated_at",
        ]

    def get_fields(self):
        fields = super().get_fields()

        if self.instance is not None:
            fields["product"].read_only = True
            fields["warehouse"].read_only = True

        return fields

    @extend_schema_field(serializers.IntegerField())
    def get_available_quantity(self, obj):
        return obj.quantity - obj.reserved_quantity

    @extend_schema_field(serializers.BooleanField())
    def get_is_low_stock(self, obj):
        return self.get_available_quantity(obj) <= obj.reorder_level

    def validate(self, attrs):
        product = attrs.get(
            "product", getattr(self.instance, "product", None)
        )
        warehouse = attrs.get(
            "warehouse", getattr(self.instance, "warehouse", None)
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


class StockReconciliationSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.filter(is_active=True)
    )
    physical_count = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        default="Physical stock reconciliation",
    )


class StockMovementSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(
        source="product.sku", read_only=True
    )
    warehouse_code = serializers.CharField(
        source="warehouse.code", read_only=True
    )
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )

    class Meta:
        model = StockMovement
        fields = [
            "id", "product", "product_sku", "warehouse",
            "warehouse_code", "quantity", "movement_type",
            "reason", "created_by", "created_by_username", "created_at",
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
                    "Transfers must be performed through "
                    "the warehouse transfer service."
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


class StockTransferSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.filter(is_active=True))
    source_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.filter(is_active=True))
    destination_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.filter(is_active=True))
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255, default="Warehouse transfer")

    def validate(self, attrs):
        if attrs["source_warehouse"].pk == attrs["destination_warehouse"].pk:
            raise serializers.ValidationError({"destination_warehouse": "Source and destination warehouses must be different."})
        return attrs


class OrderItemCreateSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True)
    )
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    # Order model uses max_length=30.
    order_number = serializers.CharField(
        max_length=30, trim_whitespace=True
    )
    warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.filter(is_active=True)
    )
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    items = OrderItemCreateSerializer(many=True, allow_empty=False)

    def validate_order_number(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError(
                "Order number cannot be empty."
            )
        if Order.objects.filter(order_number=value).exists():
            raise serializers.ValidationError(
                "This order number already exists."
            )
        return value

    def validate_items(self, items):
        product_ids = [item["product"].id for item in items]

        if len(product_ids) != len(set(product_ids)):
            raise serializers.ValidationError(
                "A product can appear only once in an order."
            )

        return items

    def create(self, validated_data):
        from apps.catalog.services import create_order

        return create_order(
            order_number=validated_data["order_number"],
            customer=validated_data.get("customer"),
            warehouse=validated_data["warehouse"],
            items=validated_data["items"],
            created_by=self.context["request"].user,
        )



class OrderItemReadSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(
        source="product.sku", read_only=True
    )
    product_name = serializers.CharField(
        source="product.name", read_only=True
    )
    subtotal = serializers.DecimalField(
        max_digits=24, decimal_places=2, read_only=True
    )
    remaining_quantity = serializers.IntegerField(read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_sku",
            "product_name",
            "quantity",
            "fulfilled_quantity",
            "remaining_quantity",
            "unit_price",
            "subtotal",
        ]
        read_only_fields = fields


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_username = serializers.CharField(
        source="changed_by.username", read_only=True, allow_null=True
    )

    class Meta:
        model = OrderStatusHistory
        fields = ["id", "from_status", "to_status", "changed_by", "changed_by_username", "note", "created_at"]
        read_only_fields = fields


class OrderReadSerializer(serializers.ModelSerializer):
    items = OrderItemReadSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    warehouse_code = serializers.CharField(
        source="warehouse.code", read_only=True
    )
    customer_name = serializers.CharField(
        source="customer.name", read_only=True, allow_null=True
    )
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )
    total_amount = serializers.DecimalField(
        max_digits=24, decimal_places=2, read_only=True
    )

    class Meta:
        model = Order
        fields = [
            "id", "order_number", "customer", "customer_name",
            "warehouse", "warehouse_code", "created_by",
            "created_by_username", "status", "items", "status_history",
            "total_amount", "expires_at", "created_at", "updated_at",
        ]
        read_only_fields = fields
