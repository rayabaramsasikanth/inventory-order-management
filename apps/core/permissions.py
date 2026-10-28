
from rest_framework.permissions import BasePermission


# Keep role names consistent with the Django Groups we create.
ADMIN_GROUP = "Admin"
WAREHOUSE_GROUP = "Warehouse Staff"
SALES_GROUP = "Sales Staff"


class IsAdminUser(BasePermission):
    """Allow access to administrators only."""

    def has_permission(self, request, view):
        user = request.user

        if not user.is_authenticated:
            return False

        # Django superusers always have administrator access.
        if user.is_superuser:
            return True

        # Regular users need membership in the Admin group.
        return user.groups.filter(name=ADMIN_GROUP).exists()


class IsWarehouseStaff(BasePermission):
    """Allow access to warehouse operations."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.groups.filter(name=WAREHOUSE_GROUP).exists()
        )


class IsSalesStaff(BasePermission):
    """Allow access to sales and order operations."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.groups.filter(name=SALES_GROUP).exists()
        )