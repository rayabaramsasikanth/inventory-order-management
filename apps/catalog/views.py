
from django.core.exceptions import ValidationError as DjangoValidationError

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import (
    Customer,
    Inventory,
    Order,
    Product,
    StockMovement,
    Supplier,
    Warehouse,
)
from apps.catalog.serializers import (
    CustomerSerializer,
    InventorySerializer,
    OrderCreateSerializer,
    OrderReadSerializer,
    ProductSerializer,
    StockMovementSerializer,
    StockReconciliationSerializer,
    SupplierSerializer,
    WarehouseSerializer,
)

from apps.catalog.services import (
    fulfil_order,
    reconcile_stock,
    record_stock_movement,
    update_order_status,
)

from apps.core.permissions import (
    IsAdminUser as IsBusinessAdmin,
    IsSalesStaff,
    IsWarehouseStaff,
)


class SupplierListCreateView(generics.ListCreateAPIView):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBusinessAdmin()]

        return super().get_permissions()


class SupplierDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsBusinessAdmin]


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

        return super().get_permissions()


class CustomerDetailView(generics.RetrieveUpdateAPIView):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]


class ProductListCreateView(generics.ListCreateAPIView):
    queryset = Product.objects.select_related("supplier").all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    filter_backends = [
        filters.SearchFilter,
        DjangoFilterBackend,
        filters.OrderingFilter,
    ]
    search_fields = ["name", "sku", "description"]
    filterset_fields = ["supplier", "is_active"]
    ordering_fields = ["name", "selling_price", "created_at"]
    ordering = ["name"]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBusinessAdmin()]

        return super().get_permissions()


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.select_related("supplier").all()
    serializer_class = ProductSerializer
    permission_classes = [IsBusinessAdmin]


class WarehouseListCreateView(generics.ListCreateAPIView):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBusinessAdmin()]

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

    def get_permissions(self):
        if self.request.method == "POST":
            return [(IsBusinessAdmin | IsWarehouseStaff)()]

        return super().get_permissions()


class StockReconciliationView(generics.GenericAPIView):
    serializer_class = StockReconciliationSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [(IsBusinessAdmin | IsWarehouseStaff)()]

        return super().get_permissions()

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

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
    queryset = Inventory.objects.select_related(
        "product",
        "warehouse",
    ).all()
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method in {"PUT", "PATCH", "DELETE"}:
            return [(IsBusinessAdmin | IsWarehouseStaff)()]

        return super().get_permissions()


class StockMovementListCreateView(generics.ListCreateAPIView):
    serializer_class = StockMovementSerializer

    def get_queryset(self):
        return StockMovement.objects.select_related(
            "product",
            "warehouse",
            "created_by",
        ).all()

    def get_permissions(self):
        if self.request.method in {"GET", "POST"}:
            return [(IsBusinessAdmin | IsWarehouseStaff)()]

        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

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


class OrderListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Order.objects
            .select_related("customer", "warehouse", "created_by")
            .prefetch_related("items__product")
            .order_by("-created_at")
        )

    def get_permissions(self):
        if self.request.method == "POST":
            return [(IsBusinessAdmin | IsSalesStaff)()]

        return super().get_permissions()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return OrderCreateSerializer

        return OrderReadSerializer


class OrderDetailView(generics.RetrieveAPIView):
    queryset = (
        Order.objects
        .select_related("customer", "warehouse", "created_by")
        .prefetch_related("items__product")
    )
    serializer_class = OrderReadSerializer
    permission_classes = [IsAuthenticated]


class OrderStatusUpdateView(generics.GenericAPIView):
    queryset = Order.objects.select_related(
        "customer",
        "warehouse",
        "created_by",
    ).prefetch_related("items__product")
    serializer_class = OrderReadSerializer
    permission_classes = [
        IsAuthenticated & (IsBusinessAdmin | IsSalesStaff)
    ]

    def patch(self, request, *args, **kwargs):
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


class OrderFulfilmentView(generics.GenericAPIView):
    queryset = (
        Order.objects
        .select_related("customer", "warehouse", "created_by")
        .prefetch_related("items__product")
    )
    serializer_class = OrderReadSerializer
    permission_classes = [
        IsAuthenticated & (IsBusinessAdmin | IsWarehouseStaff)
    ]

    def post(self, request, *args, **kwargs):
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
