from django.conf import settings
from django.db import models

# Create your models here.
class Supplier(models.Model):
    # Company or supplier name.
    name = models.CharField(max_length=150)

    # Unique business email for supplier communication.
    email = models.EmailField(unique=True)

    # Contact number; stored as text to support +, spaces, and country codes.
    phone = models.CharField(max_length=20, blank=True)

    # Supplier's business address.
    address = models.TextField(blank=True)

    # Allows the business to deactivate a supplier without deleting its history.
    is_active = models.BooleanField(default=True)

    # Automatically record when the supplier was created.
    created_at = models.DateTimeField(auto_now_add=True)

    # Update this timestamp whenever the supplier record changes.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Display suppliers in alphabetical order.
        ordering = ["name"]

    def __str__(self):
        # Show the supplier name in Django admin and the shell.
        return self.name


class Product(models.Model):
    # Unique stock-keeping unit used to identify a product.
    sku = models.CharField(max_length=50, unique=True)

    # Product name shown in the catalog.
    name = models.CharField(max_length=200)

    # Optional product details.
    description = models.TextField(blank=True)

    # The supplier that provides this product.
    # PROTECT prevents deleting a supplier while products reference it.
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="products",
    )

    # Cost paid to the supplier, stored accurately as a decimal.
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    # Price charged to the customer.
    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    # Prevent new business operations on discontinued products.
    is_active = models.BooleanField(default=True)

    # Automatically track when the product was created.
    created_at = models.DateTimeField(auto_now_add=True)

    # Automatically update this field whenever the record changes.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Display products alphabetically.
        ordering = ["name"]

    def __str__(self):
        # Include the SKU to make products easy to identify.
        return f"{self.sku} - {self.name}"


class Warehouse(models.Model):
    # Name of the physical storage location.
    name = models.CharField(max_length=150)

    # Unique code used to identify a warehouse.
    code = models.CharField(max_length=30, unique=True)

    # Warehouse address.
    address = models.TextField(blank=True)

    # Allow a warehouse to be deactivated without deleting its history.
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Inventory(models.Model):
    # The product being stored.
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="inventory_records",
    )

    # The warehouse holding this product.
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="inventory_records",
    )

    # Physical quantity currently held in this warehouse.
    quantity = models.PositiveIntegerField(default=0)

    # Quantity reserved for orders but not yet fulfilled.
    reserved_quantity = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # A product should have only one stock record per warehouse.
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
    # Define the types of stock changes supported by the system.
    class MovementType(models.TextChoices):
        RECEIPT = "RECEIPT", "Receipt"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        ISSUE = "ISSUE", "Issue"
        TRANSFER_IN = "TRANSFER_IN", "Transfer In"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer Out"

    # Product whose stock changed.
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    # Warehouse where the stock movement occurred.
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    # Positive or negative quantity change.
    quantity = models.IntegerField()

    # Reason/category for the stock change.
    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
    )

    # Optional explanation for manual adjustments.
    reason = models.CharField(
        max_length=255,
        blank=True,
    )

    # User responsible for the stock change.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    # Automatically record when the movement was created.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.product.sku} - "
            f"{self.warehouse.code} - "
            f"{self.quantity}"
        )
