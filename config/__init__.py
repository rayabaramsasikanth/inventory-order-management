# Keep Django usable for contributors who have not installed the optional
# worker dependencies yet. Install requirements.txt to enable Celery workers.
try:
    from .celery import app as celery_app
except ImportError:  # pragma: no cover - exercised only without Celery installed
    celery_app = None

__all__ = ("celery_app",)
