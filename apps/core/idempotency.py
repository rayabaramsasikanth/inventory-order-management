"""Database-backed idempotency for retryable write requests."""
import hashlib
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework import status

from apps.core.models import IdempotencyRecord

logger = logging.getLogger("apps.idempotency")


def execute_idempotently(request, operation):
    """Replay a stored response for the same user/key/request fingerprint.

    The header is optional for backward compatibility. Clients should send a
    unique Idempotency-Key for order creation, stock movements, reconciliation
    and fulfilment. A reused key with a different payload receives HTTP 409.
    """
    key = request.headers.get("Idempotency-Key")
    if not key:
        return operation()
    if len(key) > 128 or any(ord(char) < 33 or ord(char) > 126 for char in key):
        return Response(
            {"detail": "Idempotency-Key must be 1-128 printable ASCII characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    fingerprint_source = json.dumps(
        {"method": request.method, "path": request.path, "data": request.data},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    now = timezone.now()
    ttl = int(getattr(settings, "IDEMPOTENCY_TTL_SECONDS", 86400))

    with transaction.atomic():
        record, created = IdempotencyRecord.objects.get_or_create(
            user=request.user,
            key=key,
            defaults={
                "request_hash": fingerprint,
                "state": IdempotencyRecord.State.PROCESSING,
                "expires_at": now + timedelta(seconds=ttl),
            },
        )
        if not created:
            record = IdempotencyRecord.objects.select_for_update().get(pk=record.pk)
            if record.expires_at <= now:
                record.delete()
                record = IdempotencyRecord.objects.create(
                    user=request.user,
                    key=key,
                    request_hash=fingerprint,
                    state=IdempotencyRecord.State.PROCESSING,
                    expires_at=now + timedelta(seconds=ttl),
                )
            elif record.request_hash != fingerprint:
                return Response(
                    {"detail": "This Idempotency-Key was already used with a different request."},
                    status=status.HTTP_409_CONFLICT,
                )
            elif record.state == IdempotencyRecord.State.COMPLETED:
                return Response(record.response_body, status=record.response_status or 200)
            else:
                return Response(
                    {"detail": "A request with this Idempotency-Key is still processing."},
                    status=status.HTTP_409_CONFLICT,
                )

        response = operation()
        if response.status_code >= 500:
            # Do not cache transient server failures; let the client retry.
            record.delete()
            return response

        try:
            body = json.loads(JSONRenderer().render(response.data).decode("utf-8"))
        except (TypeError, ValueError):
            body = {"detail": "Response could not be stored for replay."}
        record.response_status = response.status_code
        record.response_body = body
        record.state = IdempotencyRecord.State.COMPLETED
        record.save(update_fields=["response_status", "response_body", "state"])
        return response
