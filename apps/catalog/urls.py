
from django.urls import path

from apps.catalog.views import (
    ProductCategoryListCreateView,
    ProductCategoryDetailView,
    UnitOfMeasureListCreateView,
    UnitOfMeasureDetailView,
    CustomerDetailView,
    CustomerListCreateView,
    InventoryDetailView,
    InventoryListCreateView,
    OrderDetailView,
    OrderFulfilmentView,
    OrderListCreateView,
    OrderStatusUpdateView,
    ProductDetailView,
    ProductListCreateView,
    StockMovementListCreateView,
    StockReconciliationView,
    StockTransferView,
    SupplierDetailView,
    SupplierListCreateView,
    WarehouseDetailView,
    WarehouseListCreateView,
)

urlpatterns = [
    path("categories/", ProductCategoryListCreateView.as_view(), name="category-list-create"),
    path("categories/<int:pk>/", ProductCategoryDetailView.as_view(), name="category-detail"),
    path("units/", UnitOfMeasureListCreateView.as_view(), name="unit-list-create"),
    path("units/<int:pk>/", UnitOfMeasureDetailView.as_view(), name="unit-detail"),
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
    ),
    path(
        "inventory/<int:pk>/",
        InventoryDetailView.as_view(),
        name="inventory-detail",
    ),
    path(
        "inventory/reconcile/",
        StockReconciliationView.as_view(),
        name="inventory-reconcile",
    ),
    path("stock-transfers/", StockTransferView.as_view(), name="stock-transfer"),
    path(
        "stock-movements/",
        StockMovementListCreateView.as_view(),
        name="stock-movement-list-create",
    ),
    path(
        "customers/",
        CustomerListCreateView.as_view(),
        name="customer-list-create",
    ),
    path(
        "customers/<int:pk>/",
        CustomerDetailView.as_view(),
        name="customer-detail",
    ),
    path(
        "orders/",
        OrderListCreateView.as_view(),
        name="order-list-create",
    ),
    path(
        "orders/<int:pk>/",
        OrderDetailView.as_view(),
        name="order-detail",
    ),
    path(
        "orders/<int:pk>/status/",
        OrderStatusUpdateView.as_view(),
        name="order-status-update",
    ),
    path(
        "orders/<int:pk>/fulfil/",
        OrderFulfilmentView.as_view(),
        name="order-fulfilment",
    ),
]
