# Inventory & Order Management API

Django REST Framework inventory/order API. See [`PHASE_1_TO_3_GUIDE.md`](PHASE_1_TO_3_GUIDE.md) for the implementation map, database decision, new endpoints, Redis/Celery configuration, migrations and verification commands.

## Quick start (Windows PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
```

Keep your real `.env`, `.venv`, `.git` and local database. `.env.example` contains placeholders only; do not replace your real `.env` with it.

The active database remains SQLite until Phase 2 is accepted. AWS RDS PostgreSQL is intentionally deferred. Redis/Celery are wired but require a reachable `REDIS_URL` before real asynchronous workers and Redis-backed cache/throttling can operate across processes.

API docs: `/api/docs/`; OpenAPI schema: `/api/schema/`; health: `/api/health/`.
