
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


@transaction.atomic
def transfer_stock(
    *,
    product,
    source_warehouse,
    destination_warehouse,
    quantity,
    created_by,
    reason="",
):
    """Transfer stock between warehouses as one atomic operation."""

    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or quantity <= 0
    ):
        raise ValidationError(
            "Transfer quantity must be a positive integer."
        )

    if source_warehouse.pk == destination_warehouse.pk:
        raise ValidationError(
            "Source and destination warehouses must be different."
        )

    if not product.is_active:
        raise ValidationError(
            "Cannot transfer stock for an inactive product."
        )

    if not source_warehouse.is_active:
        raise ValidationError(
            "Cannot transfer stock from an inactive warehouse."
        )

    if not destination_warehouse.is_active:
        raise ValidationError(
            "Cannot transfer stock to an inactive warehouse."
        )

    # Lock existing inventory records in a consistent order.
    warehouse_ids = sorted([
        source_warehouse.pk,
        destination_warehouse.pk,
    ])

    inventories = list(
        Inventory.objects.select_for_update()
        .filter(
            product=product,
            warehouse_id__in=warehouse_ids,
        )
        .order_by("warehouse_id")
    )

    inventory_by_warehouse = {
        inventory.warehouse_id: inventory
        for inventory in inventories
    }

    source_inventory = inventory_by_warehouse.get(
        source_warehouse.pk
    )

    if source_inventory is None:
        raise ValidationError(
            "No source inventory record exists for this product."
        )

    available_quantity = (
        source_inventory.quantity
        - source_inventory.reserved_quantity
    )

    if available_quantity < quantity:
        raise ValidationError(
            f"Insufficient available stock. "
            f"Available quantity: {available_quantity}."
        )

    destination_inventory = inventory_by_warehouse.get(
        destination_warehouse.pk
    )

    if destination_inventory is None:
        destination_inventory = Inventory.objects.create(
            product=product,
            warehouse=destination_warehouse,
            quantity=0,
        )

    # Update both inventories within the same transaction.
    source_inventory.quantity -= quantity
    destination_inventory.quantity += quantity

    source_inventory.save(
        update_fields=["quantity", "updated_at"]
    )
    destination_inventory.save(
        update_fields=["quantity", "updated_at"]
    )

    # Record both sides of the transfer for auditing.
    movements = StockMovement.objects.bulk_create([
        StockMovement(
            product=product,
            warehouse=source_warehouse,
            quantity=-quantity,
            movement_type=StockMovement.MovementType.TRANSFER_OUT,
            reason=reason,
            created_by=created_by,
        ),
        StockMovement(
            product=product,
            warehouse=destination_warehouse,
            quantity=quantity,
            movement_type=StockMovement.MovementType.TRANSFER_IN,
            reason=reason,
            created_by=created_by,
        ),
    ])

    return movements
