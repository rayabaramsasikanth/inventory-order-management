from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # Existing/admin-created users remain verified by default. Public
    # registration explicitly sets this to False until email verification.
    email_verified = models.BooleanField(default=True)


class IdempotencyRecord(models.Model):
    """Persist API responses so retries cannot repeat critical writes."""

    class State(models.TextChoices):
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="idempotency_records",
    )
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=12, choices=State.choices, default=State.PROCESSING)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "key"], name="unique_user_idempotency_key"),
        ]
        indexes = [models.Index(fields=["state", "expires_at"], name="idempotency_state_exp_idx")]

    def __str__(self):
        return f"{self.user_id}:{self.key}"
