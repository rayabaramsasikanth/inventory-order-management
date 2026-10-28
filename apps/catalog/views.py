from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.catalog.models import (
    Product,
    Supplier,
    Warehouse,
    StockMovement,
    Inventory,
)
from apps.catalog.serializers import (
    ProductSerializer,
    SupplierSerializer,
    WarehouseSerializer,
    StockMovementSerializer,
    InventorySerializer,
)

from apps.catalog.services import record_stock_movement

from apps.core.permissions import (
    IsAdminUser as IsBusinessAdmin,
    IsWarehouseStaff,
    IsSalesStaff,
)

class SupplierListCreateView(generics.ListCreateAPIView):
    # GET lists suppliers; POST creates a supplier.
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Any authenticated user can list suppliers.
        # Only business administrators can create suppliers.
        if self.request.method == "POST":
            return [IsBusinessAdmin()]

        return super().get_permissions()


class SupplierDetailView(generics.RetrieveUpdateDestroyAPIView):
    # GET, PUT, PATCH, and DELETE operate on one supplier.
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsBusinessAdmin]


class ProductListCreateView(generics.ListCreateAPIView):
    # Fetch product and supplier data efficiently.
    queryset = Product.objects.select_related("supplier").all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Authenticated users can list; administrators can create.
        if self.request.method == "POST":
            return [IsBusinessAdmin()]

        return super().get_permissions()


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    # Fetch the related supplier in the same database query.
    queryset = Product.objects.select_related("supplier").all()
    serializer_class = ProductSerializer
    permission_classes = [IsBusinessAdmin]


class WarehouseListCreateView(generics.ListCreateAPIView):
    # Authenticated users can list warehouses.
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Only administrators can register a warehouse.
        if self.request.method == "POST":
            return [IsBusinessAdmin()]

        return super().get_permissions()


class WarehouseDetailView(generics.RetrieveUpdateDestroyAPIView):
    # Only administrators can manage individual warehouses.
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsBusinessAdmin]


class InventoryListCreateView(generics.ListCreateAPIView):
    # Fetch related product and warehouse data efficiently.
    queryset = Inventory.objects.select_related(
        "product",
        "warehouse",
    ).all()
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Only administrators and warehouse staff can create stock records.
        if self.request.method == "POST":
            return [IsBusinessAdmin() | IsWarehouseStaff()]

        # Authenticated users can list inventory.
        return super().get_permissions()


class InventoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Inventory.objects.select_related(
        "product",
        "warehouse",
    ).all()
    serializer_class = InventorySerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Only administrators and warehouse staff can change inventory.
        if self.request.method in ["PUT", "PATCH", "DELETE"]:
            return [IsBusinessAdmin() | IsWarehouseStaff()]

        # Authenticated users can retrieve an individual stock record.
        return super().get_permissions()


class StockMovementListCreateView(generics.ListCreateAPIView):
    serializer_class = StockMovementSerializer

    def get_queryset(self):
        # Show movement history newest first.
        return StockMovement.objects.select_related(
            "product",
            "warehouse",
            "created_by",
        ).all()

    def get_permissions(self):
        # Only Admin and Warehouse Staff can access this endpoint.
        if self.request.method in ["GET", "POST"]:
            return [(IsBusinessAdmin | IsWarehouseStaff) ()]

        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        # Validate the incoming request before changing stock.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:
            # Update inventory and save the audit record together.
            movement = record_stock_movement(
                product=data["product"],
                warehouse=data["warehouse"],
                quantity=data["quantity"],
                movement_type=data["movement_type"],
                reason=data.get("reason", ""),
                created_by=request.user,
            )
        except ValidationError as exc:
            raise ValidationError({"detail": exc.messages})

        # Return the saved movement with read-only display fields.
        response_serializer = self.get_serializer(movement)

        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
        )
