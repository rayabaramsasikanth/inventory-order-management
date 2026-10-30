import logging

from celery import shared_task
from django.db import OperationalError
from django.utils import timezone

from apps.core.models import IdempotencyRecord

logger = logging.getLogger("apps.core.tasks")


@shared_task(
    bind=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def cleanup_idempotency_records(self):
    deleted, _ = IdempotencyRecord.objects.filter(expires_at__lte=timezone.now()).delete()
    logger.info("Cleaned expired idempotency records count=%s", deleted)
    return {"deleted": deleted}
