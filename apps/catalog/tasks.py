import logging
import smtplib
import uuid
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import OperationalError
from django.db.models import F, ExpressionWrapper, IntegerField
from django.utils import timezone
from django.core.cache import cache

from apps.catalog.models import Inventory, Order
from apps.catalog.services import cancel_order

logger = logging.getLogger("apps.catalog.tasks")


def _acquire_task_lock(name, timeout=1800):
    token = uuid.uuid4().hex
    acquired = cache.add(f"task-lock:{name}", token, timeout=timeout)
    return token if acquired else None


def _release_task_lock(name, token):
    key = f"task-lock:{name}"
    if token and cache.get(key) == token:
        cache.delete(key)


@shared_task(
    bind=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    time_limit=600,
    soft_time_limit=540,
)
def expire_pending_orders(self):
    """Release reservations for pending orders whose hold period elapsed."""
    lock_name = "expire-pending-orders"
    token = _acquire_task_lock(lock_name, timeout=900)
    if not token:
        logger.info("Skipped overlapping expire_pending_orders run")
        return {"expired": 0, "skipped": True}

    expired_count = 0
    try:
        now = timezone.now()
        order_ids = list(
            Order.objects.filter(
                status=Order.Status.PENDING,
                expires_at__isnull=False,
                expires_at__lte=now,
            ).order_by("expires_at").values_list("id", flat=True)[:500]
        )
        for order_id in order_ids:
            try:
                cancel_order(order_id=order_id, cancelled_by=None)
                expired_count += 1
            except ValidationError:
                # The order may have been confirmed/cancelled by a user after
                # the candidate list was read. The service rechecks under lock.
                continue
        logger.info("Expired pending orders count=%s", expired_count)
        return {"expired": expired_count, "skipped": False}
    finally:
        _release_task_lock(lock_name, token)


@shared_task(
    bind=True,
    autoretry_for=(OperationalError, smtplib.SMTPException, OSError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    time_limit=600,
    soft_time_limit=540,
)
def send_low_stock_report(self):
    """Build and optionally email a compact low-stock report."""
    lock_name = "daily-low-stock-report"
    token = _acquire_task_lock(lock_name, timeout=1800)
    if not token:
        logger.info("Skipped overlapping low-stock report run")
        return {"sent": False, "skipped": True, "items": 0}

    try:
        available_expression = ExpressionWrapper(
            F("quantity") - F("reserved_quantity"), output_field=IntegerField()
        )
        low_stock = (
            Inventory.objects.select_related("product", "warehouse")
            .annotate(available_units=available_expression)
            .filter(available_units__lte=F("reorder_level"))
            .order_by("warehouse_id", "product_id")[:5000]
        )
        rows = [
            {
                "sku": item.product.sku,
                "product": item.product.name,
                "warehouse": item.warehouse.code,
                "on_hand": item.quantity,
                "reserved": item.reserved_quantity,
                "available": item.available_units,
                "reorder_level": item.reorder_level,
            }
            for item in low_stock
        ]
        recipient = getattr(settings, "LOW_STOCK_REPORT_EMAIL", "")
        if recipient:
            lines = [
                f"{row['sku']} | {row['warehouse']} | available={row['available']} | reorder={row['reorder_level']}"
                for row in rows
            ] or ["No products are currently below their reorder level."]
            send_mail(
                "Daily low-stock report",
                "\n".join(lines),
                settings.DEFAULT_FROM_EMAIL,
                [recipient],
                fail_silently=False,
            )
            return {"sent": True, "skipped": False, "items": len(rows)}
        return {"sent": False, "skipped": False, "items": len(rows), "reason": "LOW_STOCK_REPORT_EMAIL not configured"}
    finally:
        _release_task_lock(lock_name, token)


@shared_task(
    bind=True,
    autoretry_for=(OperationalError, smtplib.SMTPException, OSError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    time_limit=600,
    soft_time_limit=540,
)
def send_daily_order_report(self):
    """Email yesterday's order count and revenue summary when configured."""
    from decimal import Decimal
    from django.db.models import DecimalField, Sum, F
    from apps.catalog.models import OrderItem

    lock_name = "daily-order-report"
    token = _acquire_task_lock(lock_name, timeout=1800)
    if not token:
        logger.info("Skipped overlapping daily order report run")
        return {"sent": False, "skipped": True}

    try:
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        orders = Order.objects.filter(created_at__date=yesterday)
        revenue = OrderItem.objects.filter(
            order__created_at__date=yesterday, order__status=Order.Status.FULFILLED
        ).aggregate(
            total=Sum(
                F("unit_price") * F("quantity"),
                output_field=DecimalField(max_digits=24, decimal_places=2),
            )
        )["total"] or Decimal("0.00")
        count = orders.count()
        recipient = getattr(settings, "DAILY_ORDER_REPORT_EMAIL", "")
        if recipient:
            send_mail(
                f"Daily order report - {yesterday.isoformat()}",
                f"Orders created: {count}\nFulfilled order value: {revenue}",
                settings.DEFAULT_FROM_EMAIL,
                [recipient],
                fail_silently=False,
            )
            return {"sent": True, "date": yesterday.isoformat(), "orders": count, "revenue": str(revenue)}
        return {"sent": False, "date": yesterday.isoformat(), "orders": count, "revenue": str(revenue), "reason": "DAILY_ORDER_REPORT_EMAIL not configured"}
    finally:
        _release_task_lock(lock_name, token)
