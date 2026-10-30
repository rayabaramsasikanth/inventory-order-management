from rest_framework.permissions import BasePermission

ADMIN_GROUP = "Admin"
WAREHOUSE_GROUP = "Warehouse Staff"
SALES_GROUP = "Sales Staff"


def is_admin(user):
    return bool(
        user and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name=ADMIN_GROUP).exists())
    )


def is_warehouse_staff(user):
    return bool(user and user.is_authenticated and user.groups.filter(name=WAREHOUSE_GROUP).exists())


def is_sales_staff(user):
    return bool(user and user.is_authenticated and user.groups.filter(name=SALES_GROUP).exists())


def assigned_warehouse_ids(user):
    if not user or not user.is_authenticated:
        return []
    return user.assigned_warehouses.values_list("id", flat=True)


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return is_admin(request.user)


class IsWarehouseStaff(BasePermission):
    def has_permission(self, request, view):
        return is_warehouse_staff(request.user)


class IsSalesStaff(BasePermission):
    def has_permission(self, request, view):
        return is_sales_staff(request.user)
