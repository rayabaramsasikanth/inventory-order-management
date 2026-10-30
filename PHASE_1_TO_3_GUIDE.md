# Inventory & Order Management — Phase 1 to Phase 3 implementation

This package is based on the uploaded `inventory-project.zip` and preserves the existing Django REST Framework business APIs. It is designed to be overlaid onto the existing Windows project folder; do not replace the user's `.env`, `.venv`, `.git`, or SQLite database.

## Database decision for this delivery

**SQLite remains the active database.** No AWS RDS instance, PostgreSQL server, database credentials, VPC, security group, or database migration to AWS is created in this phase. The existing settings already support PostgreSQL later through `DATABASE_ENGINE=postgresql`; do not switch that setting until Phase 2 has been functionally completed and the AWS RDS database is provisioned.

The current inventory quantities are whole-number units. The Unit of Measure catalog records whole-unit codes such as `EA`, `BOX`, and `CASE`. Fractional stock quantities are intentionally not enabled because the existing inventory/order ledger stores integer quantities. A future decimal-quantity migration must change inventory, reservations, movements, and order-item quantities together.

## Phase 1 — Foundation, authentication, permissions and security

Existing foundation retained:
- Django 6.1, DRF, custom `core.User`, `.env` loading, Git ignore rules, health endpoint, JWT access/refresh tokens and token blacklist.
- Role groups: `Admin`, `Warehouse Staff`, and `Sales Staff`.
- Password validation, login/registration/password-reset throttling, OpenAPI schema and Swagger UI.

Added/strengthened:
- Public registration creates an unverified account and sends a verification email.
- `POST /api/auth/verify-email/` verifies `uid` and `token`; `POST /api/auth/verify-email/resend/` resends without revealing whether an account exists.
- Unverified users cannot log in. Existing/admin-created users remain verified by default for backwards compatibility.
- `POST /api/auth/deactivate/` requires the current password, disables the account and blacklists its outstanding refresh tokens.
- Password change and password reset continue to invalidate outstanding refresh tokens.
- Logout verifies that the refresh token belongs to the authenticated user.
- Warehouse staff are limited to warehouses assigned to them; stock movement, reconciliation, transfer, inventory and fulfilment enforce assignment checks.
- CORS is opt-in through `CORS_ALLOWED_ORIGINS`; CSRF middleware remains enabled. HTTPS/cookie/HSTS settings are environment-controlled for a future HTTPS deployment.

Email in local development uses Django's console backend by default. Registration and password-reset links appear in the Django terminal; they are not returned in API responses.

## Phase 2 — Business logic

Existing workflows retained:
- Suppliers, customers, products, warehouses, inventory, stock ledger, receipts/issues/adjustments, stock reconciliation and transfer service.
- Order creation, stock reservation, cancellation, partial fulfilment, allowed status transitions and immutable order status history.
- Database constraints for non-negative prices, unique product/warehouse inventory, reserved quantity bounds and order-item quantities.
- Filtering, searching, ordering, pagination, versioned catalog URLs and query optimization already present in the uploaded project.

Added:
- Product categories: `/api/catalog/categories/` and `/api/v1/catalog/categories/`.
- Units of measure: `/api/catalog/units/` and `/api/v1/catalog/units/`.
- Product category/unit fields and product filters for category and unit.
- SKU is normalized to uppercase, checked case-insensitively on creation, and made read-only on update. Product DELETE archives the SKU (`is_active=False`) rather than destroying historical references.
- Stock transfer API: `POST /api/catalog/stock-transfers/`; creates paired transfer-out and transfer-in ledger entries atomically. Warehouse staff must be assigned to both warehouses.
- New orders receive a configurable pending reservation expiry (`ORDER_RESERVATION_TTL_MINUTES`, default 30). Confirmation/processing clears the pending expiry; cancellation releases reserved quantities.
- Database-backed idempotency records. Critical write endpoints support the `Idempotency-Key` header. Repeated requests with the same user/key/payload replay the original response; reusing a key with a different payload returns HTTP 409. The header is optional for backward compatibility, so clients should always send it for retryable writes.
- Product-list caching with a short TTL, version-based invalidation and a cache lock to reduce cache stampedes.

## Phase 3 — Redis and Celery integration

Added integration code:
- When `REDIS_URL` is configured, Django's default cache uses `django-redis`. DRF throttles use Django's default cache, so throttling becomes Redis-backed.
- Without `REDIS_URL`, SQLite plus LocMemCache keeps Phase 1/2 development working. Cache errors are fail-open for API availability; throttling/cache effectiveness is degraded during a Redis outage and should be monitored.
- Celery app, JSON task serialization, late acknowledgements, worker-loss rejection, task events, bounded time limits, retries with backoff/jitter, and result expiry.
- Scheduled tasks: expire stale pending orders every five minutes, clean expired idempotency records daily, send a daily low-stock report, and send a daily order/revenue summary.
- Scheduled jobs use cache-backed locks to avoid overlapping runs. These locks are distributed when Redis is configured; LocMemCache only protects a single process.
- Report emails are optional and controlled by `LOW_STOCK_REPORT_EMAIL` and `DAILY_ORDER_REPORT_EMAIL`.

**Important runtime boundary:** The Redis/Celery code is included, but no Redis service/ElastiCache resource is created by this ZIP. Until `REDIS_URL` points to a reachable Redis endpoint, tasks run eagerly in local development and there is no multi-process background worker. Configure Redis before starting a real worker/beat process. A managed AWS Redis deployment requires the endpoint, TLS/auth details and network access to be supplied securely; no credentials belong in Git.

## New migrations

- `apps/core/migrations/0002_user_email_verified_idempotencyrecord.py`
- `apps/catalog/migrations/0012_categories_units_order_expiry.py`

Run `python manage.py migrate`; do not run `makemigrations` for these changes.

## Install and verify after overlay

In the activated `.venv`:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test
```

The added dependencies are Celery with Redis support, django-redis, and django-cors-headers. This workspace cannot access the package index and therefore cannot execute Django tests itself. Run the above in the existing Windows virtual environment and review the full output before treating the package as accepted.

## Useful API additions

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/verify-email/` | Verify email using uid/token |
| POST | `/api/auth/verify-email/resend/` | Resend verification email safely |
| POST | `/api/auth/deactivate/` | Deactivate the authenticated account |
| GET/POST | `/api/catalog/categories/` | List/create categories |
| GET/PATCH/PUT/DELETE | `/api/catalog/categories/{id}/` | Retrieve/update/archive category |
| GET/POST | `/api/catalog/units/` | List/create units of measure |
| GET/PATCH/PUT/DELETE | `/api/catalog/units/{id}/` | Retrieve/update/archive unit |
| POST | `/api/catalog/stock-transfers/` | Transfer stock between assigned warehouses |

For retryable order, stock movement, reconciliation, transfer, order-status and fulfilment writes, send a unique `Idempotency-Key` header, for example `Idempotency-Key: order-create-2026-0001`.

## Phase exit gates

Phase 1/2 source changes are present, but Phase 2 is not signed off until the user runs the full test suite and business acceptance checks in their project. PostgreSQL-specific row-locking/concurrency tests remain pending until the later AWS RDS step. Phase 3 integration is not operationally signed off until a Redis endpoint is configured and worker/beat tasks are exercised against it.

## Redis/Celery operating model (concepts)

- **Redis cache:** stores short-lived product-list responses and DRF throttle counters. Product writes advance a cache-version key instead of attempting backend-specific wildcard deletion.
- **Cache stampede lock:** the first request for a cold product-list key briefly acquires a cache lock and fills it; concurrent requests wait briefly, then recompute rather than waiting indefinitely.
- **Celery broker:** Redis transports background task messages from Django to workers.
- **Celery result backend:** stores task state/results for a limited period; it is not the source of truth for orders or inventory.
- **Distributed task lock:** Redis cache `add` prevents two workers from running the same scheduled report/expiry job simultaneously. If Redis is unavailable, cache operations fail open for API availability and scheduled jobs log/skip lock acquisition; the next beat run can retry after Redis recovers.

When a reachable Redis endpoint is supplied, set `REDIS_URL` in the private `.env` file. If `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` are blank, both automatically use `REDIS_URL`. Do not commit endpoint passwords or TLS credentials.

Worker/beat commands (run only after Redis is reachable and dependencies are installed):

```powershell
celery -A config worker -l INFO --pool=solo
celery -A config beat -l INFO
celery -A config inspect active
celery -A config inspect scheduled
```

For stable long-running workers, use WSL2/Linux rather than relying on native Windows worker support. Worker events are enabled for monitoring; task logs include task outcomes and failures.

## PostgreSQL concurrency test deferred by design

`apps/catalog/tests/test_postgres_concurrency.py` contains a concurrent stock-issue test guarded by Django's `has_select_for_update` feature flag. It is skipped on SQLite and runs once the database is changed to PostgreSQL later. It verifies two simultaneous issues cannot both consume the same last available stock. Do not treat SQLite test success as proof of PostgreSQL row-lock behaviour.
