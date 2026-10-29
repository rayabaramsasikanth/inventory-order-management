
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalog.models import (
    Customer,
    Inventory,
    Order,
    OrderItem,
    Product,
    StockMovement,
    Warehouse,
)


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
    """Record a stock change and update inventory atomically."""

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
def reconcile_stock(
    *,
    product,
    warehouse,
    physical_count,
    created_by,
    reason="Physical stock reconciliation",
):
    """Reconcile recorded stock against a physical count."""

    if (
        not isinstance(physical_count, int)
        or isinstance(physical_count, bool)
        or physical_count < 0
    ):
        raise ValidationError(
            "Physical count must be a non-negative integer."
        )

    if not product.is_active:
        raise ValidationError(
            "Cannot reconcile stock for an inactive product."
        )

    if not warehouse.is_active:
        raise ValidationError(
            "Cannot reconcile stock in an inactive warehouse."
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

    difference = physical_count - inventory.quantity

    if difference == 0:
        return None

    if physical_count < inventory.reserved_quantity:
        raise ValidationError(
            "Physical count cannot be lower than reserved stock."
        )

    return record_stock_movement(
        product=product,
        warehouse=warehouse,
        quantity=difference,
        movement_type=StockMovement.MovementType.ADJUSTMENT,
        created_by=created_by,
        reason=reason,
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

    available_quantity = inventory.quantity - inventory.reserved_quantity

    if available_quantity < quantity:
        raise ValidationError(
            f"Insufficient stock. Available quantity: {available_quantity}."
        )

    inventory.reserved_quantity += quantity
    inventory.save(update_fields=["reserved_quantity", "updated_at"])

    return inventory


@transaction.atomic
def release_reserved_stock(*, product, warehouse, quantity):
    """Release reserved stock without changing physical stock."""

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
    """Transfer stock between warehouses atomically."""

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

    source_inventory = inventory_by_warehouse.get(source_warehouse.pk)

    if source_inventory is None:
        raise ValidationError(
            "No source inventory record exists for this product."
        )

    available_quantity = (
        source_inventory.quantity - source_inventory.reserved_quantity
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

    source_inventory.quantity -= quantity
    destination_inventory.quantity += quantity

    source_inventory.save(update_fields=["quantity", "updated_at"])
    destination_inventory.save(update_fields=["quantity", "updated_at"])

    return StockMovement.objects.bulk_create([
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


@transaction.atomic
def create_order(
    *,
    order_number,
    warehouse,
    items,
    created_by,
    customer=None,
):
    """Create an order, its items, and stock reservations atomically."""

    if not isinstance(order_number, str) or not order_number.strip():
        raise ValidationError("Order number cannot be empty.")

    if not items:
        raise ValidationError("An order must contain at least one item.")

    warehouse = Warehouse.objects.select_for_update().filter(
        pk=warehouse.pk,
        is_active=True,
    ).first()

    if warehouse is None:
        raise ValidationError("Warehouse does not exist or is inactive.")

    if customer is not None:
        customer = Customer.objects.filter(
            pk=customer.pk,
            is_active=True,
        ).first()

        if customer is None:
            raise ValidationError(
                "Customer does not exist or is inactive."
            )

    product_ids = []

    for item in items:
        product = item.get("product")
        quantity = item.get("quantity")

        if product is None:
            raise ValidationError(
                "Each order item must have a product."
            )

        if (
            not isinstance(quantity, int)
            or isinstance(quantity, bool)
            or quantity <= 0
        ):
            raise ValidationError(
                "Order item quantity must be a positive integer."
            )

        product_ids.append(product.pk)

    if len(product_ids) != len(set(product_ids)):
        raise ValidationError(
            "A product can appear only once in an order."
        )

    products = {
        product.pk: product
        for product in Product.objects.select_for_update()
        .filter(pk__in=product_ids, is_active=True)
        .order_by("pk")
    }

    if len(products) != len(product_ids):
        raise ValidationError(
            "One or more products do not exist or are inactive."
        )

    order = Order.objects.create(
        order_number=order_number.strip(),
        customer=customer,
        warehouse=warehouse,
        created_by=created_by,
    )

    items_by_product = {
        item["product"].pk: item
        for item in items
    }

    for product_id in sorted(product_ids):
        product = products[product_id]
        item = items_by_product[product_id]

        reserve_stock(
            product=product,
            warehouse=warehouse,
            quantity=item["quantity"],
        )

        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=item["quantity"],
            unit_price=product.selling_price,
        )

    return order


@transaction.atomic
def cancel_order(*, order_id):
    """Cancel a pending or confirmed order and release its stock."""

    order = (
        Order.objects.select_for_update()
        .filter(pk=order_id)
        .first()
    )

    if order is None:
        raise ValidationError("Order does not exist.")

    if order.status not in {
        Order.Status.PENDING,
        Order.Status.CONFIRMED,
    }:
        raise ValidationError(
            "Only pending or confirmed orders can be cancelled."
        )

    items = list(
        order.items.select_related("product").order_by("product_id")
    )

    for item in items:
        release_reserved_stock(
            product=item.product,
            warehouse=order.warehouse,
            quantity=item.quantity,
        )

    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])

    return order


@transaction.atomic
def fulfil_order(*, order_id, fulfilled_by, quantities=None):
    """
    Fulfil all remaining quantities, or selected quantities when supplied.

    quantities format:
        {order_item_id: quantity_to_ship}
    """
    order = (
        Order.objects.select_for_update()
        .filter(pk=order_id)
        .first()
    )

    if order is None:
        raise ValidationError("Order does not exist.")

    if order.status != Order.Status.PROCESSING:
        raise ValidationError(
            "Only processing orders can be fulfilled."
        )

    items = list(
        order.items.select_related("product")
        .order_by("product_id")
    )

    if quantities is None:
        # Preserve existing behavior: ship all remaining quantities.
        quantities = {
            item.pk: item.quantity - item.fulfilled_quantity
            for item in items
            if item.fulfilled_quantity < item.quantity
        }

    if not quantities:
        raise ValidationError(
            "At least one order item quantity must be supplied."
        )

    item_by_id = {item.pk: item for item in items}

    # Validate the complete request before modifying inventory.
    for item_id, ship_quantity in quantities.items():
        if item_id not in item_by_id:
            raise ValidationError(
                "An order item does not belong to this order."
            )

        if (
            isinstance(ship_quantity, bool)
            or not isinstance(ship_quantity, int)
            or ship_quantity <= 0
        ):
            raise ValidationError(
                "Shipment quantities must be positive integers."
            )

        item = item_by_id[item_id]
        remaining = item.quantity - item.fulfilled_quantity

        if ship_quantity > remaining:
            raise ValidationError(
                f"Cannot ship {ship_quantity} units of "
                f"{item.product.sku}; only {remaining} remain."
            )

    for item_id, ship_quantity in quantities.items():
        item = item_by_id[item_id]

        inventory = (
            Inventory.objects.select_for_update()
            .filter(
                product=item.product,
                warehouse=order.warehouse,
            )
            .first()
        )

        if inventory is None:
            raise ValidationError(
                "Inventory record is missing for an order item."
            )

        if (
            inventory.reserved_quantity < ship_quantity
            or inventory.quantity < ship_quantity
        ):
            raise ValidationError(
                "Inventory does not contain the required reserved stock."
            )

        inventory.quantity -= ship_quantity
        inventory.reserved_quantity -= ship_quantity
        inventory.save(
            update_fields=[
                "quantity",
                "reserved_quantity",
                "updated_at",
            ]
        )

        item.fulfilled_quantity += ship_quantity
        item.save(update_fields=["fulfilled_quantity"])

        StockMovement.objects.create(
            product=item.product,
            warehouse=order.warehouse,
            quantity=-ship_quantity,
            movement_type=StockMovement.MovementType.ISSUE,
            reason=f"Order fulfilment: {order.order_number}",
            created_by=fulfilled_by,
        )

    all_fulfilled = all(
        item.fulfilled_quantity == item.quantity
        for item in order.items.all()
    )

    if all_fulfilled:
        order.status = Order.Status.FULFILLED

    order.save(update_fields=["status", "updated_at"])

    return order


@transaction.atomic
def update_order_status(*, order_id, new_status, updated_by):
    """Apply a valid order status transition safely."""

    order = (
        Order.objects.select_for_update()
        .filter(pk=order_id)
        .first()
    )

    if order is None:
        raise ValidationError("Order does not exist.")

    allowed_transitions = {
        Order.Status.PENDING: {
            Order.Status.CONFIRMED,
            Order.Status.CANCELLED,
        },
        Order.Status.CONFIRMED: {
            Order.Status.PROCESSING,
            Order.Status.CANCELLED,
        },
        Order.Status.PROCESSING: {
            Order.Status.FULFILLED,
        },
        Order.Status.FULFILLED: set(),
        Order.Status.CANCELLED: set(),
    }

    if new_status not in Order.Status.values:
        raise ValidationError("Invalid order status.")

    if new_status not in allowed_transitions[order.status]:
        raise ValidationError(
            f"Cannot change order status from "
            f"{order.status} to {new_status}."
        )

    if new_status == Order.Status.CANCELLED:
        return cancel_order(order_id=order.pk)

    if new_status == Order.Status.FULFILLED:
        return fulfil_order(
            order_id=order.pk,
            fulfilled_by=updated_by,
        )

    order.status = new_status
    order.save(update_fields=["status", "updated_at"])

    return order
