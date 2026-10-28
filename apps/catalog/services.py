
from django.db import transaction
from django.core.exceptions import ValidationError

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

    if quantity == 0:
        raise ValidationError("Movement quantity cannot be zero.")

    # Lock the existing inventory row while changing its stock.
    inventory = (
        Inventory.objects.select_for_update()
        .filter(product=product, warehouse=warehouse)
        .first()
    )

    # Create the inventory record if this product has no stock record here.
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

    # Never allow stock to fall below the reserved quantity.
    if new_quantity < inventory.reserved_quantity:
        raise ValidationError(
            "Stock cannot fall below the currently reserved quantity."
        )

    inventory.quantity = new_quantity
    inventory.save(update_fields=["quantity", "updated_at"])

    # Save the audit record in the same transaction.
    movement = StockMovement.objects.create(
        product=product,
        warehouse=warehouse,
        quantity=quantity,
        movement_type=movement_type,
        reason=reason,
        created_by=created_by,
    )

    return movement
