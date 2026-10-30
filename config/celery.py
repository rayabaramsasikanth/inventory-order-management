import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("inventory_order_management")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "expire-pending-orders-every-five-minutes": {
        "task": "apps.catalog.tasks.expire_pending_orders",
        "schedule": crontab(minute="*/5"),
    },
    "cleanup-idempotency-records-daily": {
        "task": "apps.core.tasks.cleanup_idempotency_records",
        "schedule": crontab(hour=2, minute=15),
    },
    "send-daily-low-stock-report": {
        "task": "apps.catalog.tasks.send_low_stock_report",
        "schedule": crontab(hour=7, minute=0),
    },
    "send-daily-order-report": {
        "task": "apps.catalog.tasks.send_daily_order_report",
        "schedule": crontab(hour=7, minute=10),
    },
}
