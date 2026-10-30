from django.contrib import admin

from .models import (
    Customer,
    Inventory,
    Order,
    OrderItem,
    OrderStatusHistory,
    Product,
    ProductCategory,
    StockMovement,
    Supplier,
    UnitOfMeasure,
    Warehouse,
)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    filter_horizontal = ("assigned_staff",)


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status", "created_at")
    search_fields = ("order__order_number", "changed_by__username")
    readonly_fields = ("order", "from_status", "to_status", "changed_by", "note", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in (
    Supplier,
    Product,
    ProductCategory,
    UnitOfMeasure,
    Customer,
    Inventory,
    StockMovement,
    Order,
    OrderItem,
):
    admin.site.register(model)
