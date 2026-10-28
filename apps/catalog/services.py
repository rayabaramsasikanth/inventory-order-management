
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalog.models import Inventory, StockMovement


@transaction.atomic
def record_stock_movement(
    *,
    product,
    warehouse,
    quantity,
    movement_type,
    created_by,
    reason="",
):
    """
    Record a stock change and update inventory atomically.

    Positive quantity adds stock.
    Negative quantity removes stock.
    """

    valid_types = {
        StockMovement.MovementType.RECEIPT,
        StockMovement.MovementType.ISSUE,
        StockMovement.MovementType.ADJUSTMENT,
    }

    if movement_type not in valid_types:
        raise ValidationError(
            "Unsupported movement type. Use RECEIPT, ISSUE, or ADJUSTMENT."
        )

    if not isinstance(quantity, int) or isinstance(quantity, bool):
        raise ValidationError("Movement quantity must be an integer.")

    if quantity == 0:
        raise ValidationError("Movement quantity cannot be zero.")

    if (
        movement_type == StockMovement.MovementType.RECEIPT
        and quantity < 0
    ):
        raise ValidationError("Receipt quantity must be positive.")

    if (
        movement_type == StockMovement.MovementType.ISSUE
        and quantity > 0
    ):
        raise ValidationError("Issue quantity must be negative.")

    if not product.is_active:
        raise ValidationError(
            "Cannot move stock for an inactive product."
        )

    if not warehouse.is_active:
        raise ValidationError(
            "Cannot move stock in an inactive warehouse."
        )

    inventory = (
        Inventory.objects.select_for_update()
        .filter(product=product, warehouse=warehouse)
        .first()
    )

    if inventory is None:
        if quantity < 0:
            raise ValidationError(
                "Cannot remove stock when no inventory record exists."
            )

        inventory = Inventory.objects.create(
            product=product,
            warehouse=warehouse,
            quantity=0,
        )

    new_quantity = inventory.quantity + quantity

    if new_quantity < 0:
        raise ValidationError(
            "Available physical stock cannot become negative."
        )

    if new_quantity < inventory.reserved_quantity:
        raise ValidationError(
            "Stock cannot fall below the currently reserved quantity."
        )

    inventory.quantity = new_quantity
    inventory.save(update_fields=["quantity", "updated_at"])

    return StockMovement.objects.create(
        product=product,
        warehouse=warehouse,
        quantity=quantity,
        movement_type=movement_type,
        reason=reason,
        created_by=created_by,
    )


@transaction.atomic
def reserve_stock(*, product, warehouse, quantity):
    """Reserve available stock without reducing physical stock."""

    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or quantity <= 0
    ):
        raise ValidationError(
            "Reservation quantity must be a positive integer."
        )

    if not product.is_active:
        raise ValidationError(
            "Cannot reserve stock for an inactive product."
        )

    if not warehouse.is_active:
        raise ValidationError(
            "Cannot reserve stock in an inactive warehouse."
        )

    inventory = (
        Inventory.objects.select_for_update()
        .filter(product=product, warehouse=warehouse)
        .first()
    )

    if inventory is None:
        raise ValidationError(
            "No inventory record exists for this product and warehouse."
        )

    available_quantity = (
        inventory.quantity - inventory.reserved_quantity
    )

    if available_quantity < quantity:
        raise ValidationError(
            f"Insufficient stock. Available quantity: {available_quantity}."
        )

    inventory.reserved_quantity += quantity
    inventory.save(update_fields=["reserved_quantity", "updated_at"])

    return inventory


@transaction.atomic
def release_reserved_stock(*, product, warehouse, quantity):
    """Release previously reserved stock without changing physical stock."""

    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or quantity <= 0
    ):
        raise ValidationError(
            "Release quantity must be a positive integer."
        )

    inventory = (
        Inventory.objects.select_for_update()
        .filter(product=product, warehouse=warehouse)
        .first()
    )

    if inventory is None:
        raise ValidationError(
            "No inventory record exists for this product and warehouse."
        )

    if inventory.reserved_quantity < quantity:
        raise ValidationError(
            "Cannot release more stock than is currently reserved."
        )

    inventory.reserved_quantity -= quantity
    inventory.save(update_fields=["reserved_quantity", "updated_at"])

    return inventory
