
from django.urls import path

from apps.catalog.views import (
    SupplierListCreateView,
    SupplierDetailView,
    ProductListCreateView,
    ProductDetailView,
    WarehouseDetailView,
    WarehouseListCreateView,
    InventoryListCreateView,
    InventoryDetailView,
    StockMovementListCreateView,
)

urlpatterns = [
    path(
        "suppliers/",
        SupplierListCreateView.as_view(),
        name="supplier-list-create",
    ),
    
    path(
        "suppliers/<int:pk>/",
        SupplierDetailView.as_view(),
        name="supplier-detail",
    ),
    
    path(
    "products/",
    ProductListCreateView.as_view(),
    name="product-list-create",
    ),
    
    path(
        "products/<int:pk>/",
        ProductDetailView.as_view(),
        name="product-detail",
    ),

    path(
        "warehouses/",
        WarehouseListCreateView.as_view(),
        name="warehouse-list-create",
    ),

    path(
        "warehouses/<int:pk>/",
        WarehouseDetailView.as_view(),
        name="warehouse-detail",
    ),

    path(
        "inventory/",
        InventoryListCreateView.as_view(),
        name="inventory-list-create",
    )
    ,

    path(
        "inventory/<int:pk>/",
        InventoryDetailView.as_view(),
        name="inventory-detail",
    ),

    path(
        "stock-movements/",
        StockMovementListCreateView.as_view(),
        name="stock-movement-list-create",
    ),
]
