
from django.core.exceptions import ValidationError as DjangoValidationError

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import (
    Customer,
    ProductCategory,
    UnitOfMeasure,
    Inventory,
    Order,
    Product,
    StockMovement,
    Supplier,
    Warehouse,
)
from apps.catalog.serializers import (
    CustomerSerializer,
    ProductCategorySerializer,
    UnitOfMeasureSerializer,
    InventorySerializer,
    OrderCreateSerializer,
    OrderReadSerializer,
    ProductSerializer,
    StockMovementSerializer,
    StockReconciliationSerializer,
    StockTransferSerializer,
    SupplierSerializer,
    WarehouseSerializer,
)

from apps.core.idempotency import execute_idempotently
from apps.catalog.cache import get_or_compute, invalidate_product_cache, product_cache_version

from apps.catalog.services import (
    fulfil_order,
    reconcile_stock,
    record_stock_movement,
    transfer_stock,
    update_order_status,
)

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)

from apps.core.permissions import (
    IsAdminUser as IsBusinessAdmin,
    IsWarehouseStaff,
    IsSalesStaff,
    is_admin,
    assigned_warehouse_ids,
)


def warehouse_scoped(queryset, user, field="warehouse_id"):
    """Restrict warehouse staff to explicitly assigned warehouses."""
    if is_admin(user):
        return queryset
    if user.groups.filter(name="Warehouse Staff").exists():
        return queryset.filter(
            **{f"{field}__in": assigned_warehouse_ids(user)}
        )
    return queryset.none()

class ProductCategoryListCreateView(generics.ListCreateAPIView):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method in {"POST"}:
            return [IsBusinessAdmin()]
        return [(IsBusinessAdmin | IsWarehouseStaff | IsSalesStaff)()]

    def perform_create(self, serializer):
        serializer.save()
        invalidate_product_cache()


class ProductCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [IsBusinessAdmin]

    def perform_update(self, serializer):
        serializer.save()
        invalidate_product_cache()

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        invalidate_product_cache()


class UnitOfMeasureListCreateView(generics.ListCreateAPIView):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBusinessAdmin()]
        return [(IsBusinessAdmin | IsWarehouseStaff | IsSalesStaff)()]

    def perform_create(self, serializer):
        serializer.save()
        invalidate_product_cache()


class UnitOfMeasureDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer
    permission_classes = [IsBusinessAdmin]

    def perform_update(self, serializer):
        serializer.save()
        invalidate_product_cache()

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        invalidate_product_cache()


class SupplierListCreateView(generics.ListCreateAPIView):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBusinessAdmin()]
        if self.request.method in {"GET", "HEAD"}:
            return [(IsBusinessAdmin | IsSalesStaff)()]
        return super().get_permissions()


class SupplierDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsBusinessAdmin | IsSalesStaff]

    def perform_update(self, serializer):
        serializer.save()
        invalidate_product_cache()

    def get_permissions(self):
        if self.request.method in {"PUT", "PATCH", "DELETE"}:
            return [IsBusinessAdmin()]
        return super().get_permissions()

@extend_schema_view(
    get=extend_schema(
        summary="List customers",
        description=(
            "Returns customers with optional filtering by active status "
            "and name search. Requires authentication."
        ),
        parameters=[
            OpenApiParameter(
                name="is_active",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Filter customers by active status.",
            ),
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Search customers by name.",
            ),
        ],
    ),
    post=extend_schema(
        summary="Create customer",
        description="Creates a customer. Requires business-admin permission.",
    ),
)
class CustomerListCreateView(generics.ListCreateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Customer.objects.all()

        # Support ?is_active=true or ?is_active=false.
        is_active = self.request.query_params.get("is_active")
        if is_active in {"true", "false"}:
            queryset = queryset.filter(is_active=(is_active == "true"))

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by("name", "id")

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBusinessAdmin()]
        if self.request.method in {"GET", "HEAD"}:
            return [(IsBusinessAdmin | IsSalesStaff)()]
        return super().get_permissions()


class CustomerDetailView(generics.RetrieveUpdateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsBusinessAdmin | IsSalesStaff]

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH"):
            return [(IsBusinessAdmin | IsSalesStaff)()]

        return super().get_permissions()


@extend_schema_view(
    get=extend_schema(
        summary="List products",
        description=(
            "Returns a paginated list of products. Supports searching, "
            "filtering by supplier and active status, and ordering."
        ),
        parameters=[
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Search product name, SKU, or description.",
            ),
            OpenApiParameter(
                name="supplier",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Filter by supplier ID.",
            ),
            OpenApiParameter(
                name="is_active",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Filter by active status.",
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description=(
                    "Order by name, selling_price, or created_at. "
                    "Prefix with '-' for descending order."
                ),
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Page number.",
            ),
            OpenApiParameter(
                name="page_size",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Results per page; maximum 100.",
            ),
        ],
    ),
    post=extend_schema(
        summary="Create product",
        description="Creates a product. Requires business-admin permission.",
    ),
)
class ProductListCreateView(generics.ListCreateAPIView):
    queryset = Product.objects.select_related("supplier", "category", "unit_of_measure").all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [
        filters.SearchFilter,
        DjangoFilterBackend,
        filters.OrderingFilter,
    ]
    search_fields = ["name", "sku", "description"]
    filterset_fields = ["supplier", "category", "unit_of_measure", "is_active"]
    ordering_fields = ["name", "selling_price", "created_at"]
    ordering = ["name"]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBusinessAdmin()]

        if self.request.method in ("GET", "HEAD"):
            return [
                (IsBusinessAdmin | IsWarehouseStaff | IsSalesStaff)()
            ]

        return super().get_permissions()

    def get_queryset(self):
        return Product.objects.select_related("supplier", "category", "unit_of_measure").all()

    def list(self, request, *args, **kwargs):
        query = request.query_params.urlencode()
        key = f"catalog:products:list:{product_cache_version()}:{request.get_host()}:{query or 'all'}"
        data = get_or_compute(key, lambda: super(ProductListCreateView, self).list(request, *args, **kwargs).data, timeout=60)
        return Response(data)

    def perform_create(self, serializer):
        serializer.save()
        invalidate_product_cache()

class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.select_related("supplier", "category", "unit_of_measure").all()
    serializer_class = ProductSerializer
    permission_classes = [IsBusinessAdmin]

    def perform_update(self, serializer):
        serializer.save()
        invalidate_product_cache()

    def perform_destroy(self, instance):
        # Keep historical stock/order foreign keys intact; retire the SKU.
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        invalidate_product_cache()


class WarehouseListCreateView(generics.ListCreateAPIView):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return warehouse_scoped(
            Warehouse.objects.all(), self.request.user, field="id"
        )

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBusinessAdmin()]
        if self.request.method in {"GET", "HEAD"}:
            return [(IsBusinessAdmin | IsWarehouseStaff)()]
        return super().get_permissions()


class WarehouseDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsBusinessAdmin]


class InventoryListCreateView(generics.ListCreateAPIView):
    queryset = Inventory.objects.select_related(
        "product",
        "warehouse",
    ).all()
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        base = Inventory.objects.select_related("product", "warehouse")
        return warehouse_scoped(base, self.request.user)

    def get_permissions(self):
        if self.request.method == "POST":
            return [(IsBusinessAdmin | IsWarehouseStaff)()]
        if self.request.method in {"GET", "HEAD"}:
            return [(IsBusinessAdmin | IsWarehouseStaff)()]
        return super().get_permissions()

    def perform_create(self, serializer):
        warehouse = serializer.validated_data["warehouse"]
        if (
            not is_admin(self.request.user)
            and not warehouse.assigned_staff.filter(pk=self.request.user.pk).exists()
        ):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not assigned to this warehouse.")
        serializer.save()

@extend_schema_view(
    post=extend_schema(
        summary="Reconcile inventory stock",
        description=(
            "Compares the physical stock count with recorded inventory "
            "and creates an adjustment movement when a difference exists. "
            "Requires business-admin or warehouse-staff permission."
        ),
        request=StockReconciliationSerializer,
        responses={
            200: OpenApiTypes.OBJECT,
            201: StockMovementSerializer,
        },
    ),
)
class StockReconciliationView(generics.GenericAPIView):
    serializer_class = StockReconciliationSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [(IsBusinessAdmin | IsWarehouseStaff)()]

        return super().get_permissions()

    def post(self, request, *args, **kwargs):
        return execute_idempotently(
            request, lambda: self._post_reconciliation(request, *args, **kwargs)
        )

    def _post_reconciliation(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        if (
            not is_admin(request.user)
            and not data["warehouse"].assigned_staff.filter(pk=request.user.pk).exists()
        ):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not assigned to this warehouse.")

        try:
            movement = reconcile_stock(
                product=data["product"],
                warehouse=data["warehouse"],
                physical_count=data["physical_count"],
                created_by=request.user,
                reason=data["reason"],
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {"detail": exc.messages}
            ) from exc

        if movement is None:
            return Response(
                {
                    "detail": "Physical count matches recorded stock.",
                    "adjustment": 0,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            StockMovementSerializer(movement).data,
            status=status.HTTP_201_CREATED,
        )


class InventoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        base = Inventory.objects.select_related("product", "warehouse")
        return warehouse_scoped(base, self.request.user)

    def get_permissions(self):
        if self.request.method in {"GET", "HEAD", "PUT", "PATCH", "DELETE"}:
            return [(IsBusinessAdmin | IsWarehouseStaff)()]
        return super().get_permissions()

class StockTransferView(generics.GenericAPIView):
    serializer_class = StockTransferSerializer
    permission_classes = [IsAuthenticated & (IsBusinessAdmin | IsWarehouseStaff)]

    @extend_schema(
        summary="Transfer stock between warehouses",
        request=StockTransferSerializer,
        responses={201: StockMovementSerializer(many=True)},
        description="Creates paired transfer-out and transfer-in ledger entries atomically. Send an Idempotency-Key header to make client retries safe.",
    )
    def post(self, request, *args, **kwargs):
        return execute_idempotently(
            request, lambda: self._transfer(request, *args, **kwargs)
        )

    def _transfer(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not is_admin(request.user):
            assigned = set(assigned_warehouse_ids(request.user))
            if data["source_warehouse"].pk not in assigned or data["destination_warehouse"].pk not in assigned:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("You must be assigned to both warehouses to transfer stock.")
        try:
            movements = transfer_stock(
                product=data["product"],
                source_warehouse=data["source_warehouse"],
                destination_warehouse=data["destination_warehouse"],
                quantity=data["quantity"],
                created_by=request.user,
                reason=data.get("reason", "Warehouse transfer"),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages}) from exc
        return Response(
            StockMovementSerializer(movements, many=True).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    get=extend_schema(
        summary="List stock movements",
        description=(
            "Returns stock movement records, including their product, "
            "warehouse, quantity, movement type, and creation details."
        ),
    ),
    post=extend_schema(
        summary="Record stock movement",
        description=(
            "Records an inventory movement. Direct transfer-in and "
            "transfer-out movements are not permitted; use the transfer "
            "workflow instead. Requires business-admin or warehouse-staff permission. "
            "Send an Idempotency-Key header to safely retry the same request."
        ),
        request=StockMovementSerializer,
        responses={201: StockMovementSerializer},
    ),
)
class StockMovementListCreateView(generics.ListCreateAPIView):
    serializer_class = StockMovementSerializer

    def get_queryset(self):
        base = StockMovement.objects.select_related(
            "product", "warehouse", "created_by",
        )
        return warehouse_scoped(base, self.request.user)

    def get_permissions(self):
        if self.request.method in {"GET", "HEAD", "POST"}:
            return [(IsBusinessAdmin | IsWarehouseStaff)()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        return execute_idempotently(
            request, lambda: self._create_movement(request, *args, **kwargs)
        )

    def _create_movement(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        if (
            not is_admin(request.user)
            and not data["warehouse"].assigned_staff.filter(pk=request.user.pk).exists()
        ):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not assigned to this warehouse.")

        try:
            movement = record_stock_movement(
                product=data["product"],
                warehouse=data["warehouse"],
                quantity=data["quantity"],
                movement_type=data["movement_type"],
                reason=data.get("reason", ""),
                created_by=request.user,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {"detail": exc.messages}
            ) from exc

        return Response(
            self.get_serializer(movement).data,
            status=status.HTTP_201_CREATED,
        )

@extend_schema_view(
    get=extend_schema(
        summary="List orders",
        description=(
            "Returns orders ordered by creation date, newest first. "
            "Requires authentication."
        ),
    ),
    post=extend_schema(
        summary="Create order",
        description=(
            "Creates an order with its items. Requires business-admin "
            "or sales-staff permission. Send an Idempotency-Key header "
            "to safely retry the same request."
        ),
        request=OrderCreateSerializer,
        responses={201: OrderReadSerializer},
    ),
)
class OrderListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Order.objects
            .select_related("customer", "warehouse", "created_by")
            .prefetch_related("items__product", "status_history__changed_by")
            .order_by("-created_at")
        )

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD"):
            return [(IsBusinessAdmin | IsSalesStaff)()]

        if self.request.method == "POST":
            return [(IsBusinessAdmin | IsSalesStaff)()]

        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return OrderCreateSerializer

        return OrderReadSerializer

    def create(self, request, *args, **kwargs):
        return execute_idempotently(
            request, lambda: super(OrderListCreateView, self).create(request, *args, **kwargs)
        )

@extend_schema(
    summary="Retrieve order",
    description="Returns an order and its items. Requires authentication.",
    responses={200: OrderReadSerializer},
)
class OrderDetailView(generics.RetrieveAPIView):
    queryset = (
        Order.objects
        .select_related("customer", "warehouse", "created_by")
        .prefetch_related("items__product", "status_history__changed_by")
    )
    serializer_class = OrderReadSerializer
    permission_classes = [
        IsAuthenticated & (IsBusinessAdmin | IsSalesStaff)
    ]

@extend_schema_view(
    patch=extend_schema(
        summary="Update order status",
        description=(
            "Updates an order's status after business-rule validation. "
            "Requires business-admin or sales-staff permission."
        ),
        request={
            "application/json": {
                "type": "object",
                "required": ["status"],
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "The requested new order status.",
                    }
                },
            }
        },
        responses={200: OrderReadSerializer},
    ),
)
class OrderStatusUpdateView(generics.GenericAPIView):
    queryset = Order.objects.select_related(
        "customer",
        "warehouse",
        "created_by",
    ).prefetch_related("items__product", "status_history__changed_by")
    serializer_class = OrderReadSerializer
    permission_classes = [
        IsAuthenticated & (IsBusinessAdmin | IsSalesStaff)
    ]

    def patch(self, request, *args, **kwargs):
        return execute_idempotently(
            request, lambda: self._update_status(request, *args, **kwargs)
        )

    def _update_status(self, request, *args, **kwargs):
        order = self.get_object()
        new_status = request.data.get("status")

        if not isinstance(new_status, str):
            raise serializers.ValidationError({
                "status": "A valid order status is required."
            })

        try:
            updated_order = update_order_status(
                order_id=order.pk,
                new_status=new_status,
                updated_by=request.user,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {"status": exc.messages}
            ) from exc

        return Response(self.get_serializer(updated_order).data)

@extend_schema_view(
    post=extend_schema(
        summary="Fulfil order",
        description=(
            "Fulfils specified quantities for order items and updates "
            "inventory through the fulfilment service. Requires "
            "business-admin or warehouse-staff permission."
        ),
        request={
            "application/json": {
                "type": "object",
                "required": ["quantities"],
                "properties": {
                    "quantities": {
                        "type": "object",
                        "description": (
                            "Mapping of order item IDs to positive "
                            "integer shipment quantities."
                        ),
                        "additionalProperties": {
                            "type": "integer",
                            "minimum": 1,
                        },
                        "example": {"1": 2, "2": 1},
                    }
                },
            }
        },
        responses={200: OrderReadSerializer},
    ),
)
class OrderFulfilmentView(generics.GenericAPIView):
    serializer_class = OrderReadSerializer

    def get_queryset(self):
        base = Order.objects.select_related(
            "customer", "warehouse", "created_by"
        ).prefetch_related("items__product", "status_history__changed_by")
        if is_admin(self.request.user):
            return base
        return base.filter(
            warehouse_id__in=assigned_warehouse_ids(self.request.user)
        )
    permission_classes = [
        IsAuthenticated & (IsBusinessAdmin | IsWarehouseStaff)
    ]

    def post(self, request, *args, **kwargs):
        return execute_idempotently(
            request, lambda: self._fulfil(request, *args, **kwargs)
        )

    def _fulfil(self, request, *args, **kwargs):
        order = self.get_object()
        quantities = request.data.get("quantities")

        if not isinstance(quantities, dict) or not quantities:
            raise serializers.ValidationError({
                "quantities": (
                    "Provide a non-empty mapping of order item IDs "
                    "to shipment quantities."
                )
            })

        parsed_quantities = {}

        for item_id, quantity in quantities.items():
            try:
                parsed_item_id = int(item_id)
            except (TypeError, ValueError):
                raise serializers.ValidationError({
                    "quantities": "Order item IDs must be integers."
                })

            if str(parsed_item_id) != str(item_id) or parsed_item_id <= 0:
                raise serializers.ValidationError({
                    "quantities": "Order item IDs must be positive integers."
                })

            if (
                isinstance(quantity, bool)
                or not isinstance(quantity, int)
                or quantity <= 0
            ):
                raise serializers.ValidationError({
                    "quantities": (
                        "Shipment quantities must be positive integers."
                    )
                })

            parsed_quantities[parsed_item_id] = quantity

        try:
            updated_order = fulfil_order(
                order_id=order.pk,
                fulfilled_by=request.user,
                quantities=parsed_quantities,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {"detail": exc.messages}
            ) from exc

        return Response(
            self.get_serializer(updated_order).data,
            status=status.HTTP_200_OK,
        )
