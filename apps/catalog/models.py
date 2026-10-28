
from django.db import models
from django.conf import settings


class Supplier(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    sku = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="products",
    )

    cost_price = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.sku} - {self.name}"


class Warehouse(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, unique=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Inventory(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="inventory_records",
    )

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="inventory_records",
    )

    # Physical quantity currently held in this warehouse.
    quantity = models.PositiveIntegerField(default=0)

    # Quantity reserved for orders but not yet fulfilled.
    reserved_quantity = models.PositiveIntegerField(default=0)

    # Minimum available stock expected before replenishment is needed.
    reorder_level = models.PositiveIntegerField(default=10)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "warehouse"],
                name="unique_product_per_warehouse",
            ),
        ]
        ordering = ["warehouse", "product"]

    def __str__(self):
        return f"{self.product.sku} at {self.warehouse.code}"


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        RECEIPT = "RECEIPT", "Receipt"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        ISSUE = "ISSUE", "Issue"
        TRANSFER_IN = "TRANSFER_IN", "Transfer In"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer Out"

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    quantity = models.IntegerField()

    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
    )

    reason = models.CharField(max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.product.sku} - "
            f"{self.warehouse.code} - "
            f"{self.quantity}"
        )
