
from rest_framework.permissions import BasePermission


# Keep role names consistent with the Django Groups we create.
ADMIN_GROUP = "Admin"
WAREHOUSE_GROUP = "Warehouse Staff"
SALES_GROUP = "Sales Staff"


class IsAdminUser(BasePermission):
    """Allow access to administrators only."""

    def has_permission(self, request, view):
        # Superusers have full administrative access.
        if request.user.is_superuser:
            return True

        # Normal users must belong to the Admin group.
        return (
            request.user.is_authenticated
            and request.user.groups.filter(name=ADMIN_GROUP).exists()
        )


class IsWarehouseStaff(BasePermission):
    """Allow access to warehouse operations."""

    def has_permission(self, request, view):
        # Anonymous users must never manage inventory.
        return (
            request.user.is_authenticated
            and request.user.groups.filter(name=WAREHOUSE_GROUP).exists()
        )


class IsSalesStaff(BasePermission):
    """Allow access to sales and order operations."""

    def has_permission(self, request, view):
        # Only authenticated users assigned to Sales Staff are allowed.
        return (
            request.user.is_authenticated
            and request.user.groups.filter(name=SALES_GROUP).exists()
        )
