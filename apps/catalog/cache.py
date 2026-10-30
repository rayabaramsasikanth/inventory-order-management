"""Small cache helpers with lock-based stampede reduction and fail-open behavior."""
import logging
import time
import uuid

from django.core.cache import cache

logger = logging.getLogger("apps.catalog.cache")


def product_cache_version():
    try:
        version = cache.get("catalog:products:version")
        if version is not None:
            return version
        version = uuid.uuid4().hex
        cache.add("catalog:products:version", version, timeout=None)
        return cache.get("catalog:products:version") or version
    except Exception:
        logger.warning("Product cache version unavailable; using a one-request key")
        return uuid.uuid4().hex


def invalidate_product_cache():
    # Versioned keys avoid backend-specific wildcard deletion.
    try:
        cache.set("catalog:products:version", uuid.uuid4().hex, timeout=None)
    except Exception:
        logger.warning("Product cache invalidation failed; requests will recompute")


def get_or_compute(key, producer, timeout=60):
    try:
        cached = cache.get(key)
    except Exception:
        logger.warning("Cache read failed; computing response without cache")
        return producer()
    if cached is not None:
        return cached

    lock_key = f"{key}:lock"
    token = uuid.uuid4().hex
    try:
        acquired = cache.add(lock_key, token, timeout=15)
    except Exception:
        logger.warning("Cache lock failed; computing response without cache")
        return producer()

    if acquired:
        try:
            try:
                cached = cache.get(key)
            except Exception:
                cached = None
            if cached is not None:
                return cached

            value = producer()
            try:
                cache.set(key, value, timeout=timeout)
            except Exception:
                logger.warning("Cache write failed; returning computed response")
            return value
        finally:
            try:
                if cache.get(lock_key) == token:
                    cache.delete(lock_key)
            except Exception:
                pass

    # A different request is populating the same key. Briefly wait, then fail
    # open by recomputing; this bounds latency even during cache outages.
    for _ in range(5):
        time.sleep(0.05)
        try:
            cached = cache.get(key)
            if cached is not None:
                return cached
        except Exception:
            break
    return producer()
