# Inventory & Order Management System
A Django REST API for managing products, suppliers, warehouses, inventory, stock movements and customer orders.

## Overview
The Inventory & Order Management System helps businesses manage their product catalogue, warehouse stock and order fulfilment through REST APIs.
It supports multiple warehouses, stock tracking, inventory operations and order processing.

## Business Workflow
**Supplier → Product → Warehouse → Inventory → Customer → Order → Stock Reservation → Order Fulfilment**

## Features
- JWT authentication and user permissions
- Product, category and supplier management
- Warehouse and inventory management
- Stock receipts, issues, transfers and reconciliation
- Customer and order management
- Stock reservation and order fulfilment
- Search, filtering, sorting and pagination
- API versioning and OpenAPI documentation
- Redis caching and Celery task configuration

## Technology Stack

| Category            | Technology                      |
|---------------------|---------------------------------|
| Language            | Python                          |
| Backend             | Django, Django REST Framework   |
| Database            | SQLite (local development)      |
| Authentication      | SimpleJWT                       |
| Filtering           | django-filter                   |
| API Documentation   | drf-spectacular                 |
| Caching             | Redis                           |
| Background Tasks    | Celery                          |
| Cloud               | AWS (planned)                   |
| Frontend            | React (planned)                 |

## Project Structure
```text
inventory-order-management/
│
├── apps/
│   ├── core/
│   └── catalog/
│
├── config/
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Installation and Setup
1. Clone the repository
```bash
git clone <repository-url>
cd inventory-order-management
```

**2. Create and activate a virtual environment**
```bash
python -m venv .venv
source .venv/Scripts/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure environment variables**
Create a `.env` file using `.env.example` as a reference.

**5. Apply migrations**
```bash
python manage.py migrate
```

**6. Start the development server**
```bash
python manage.py runserver
```

## API Documentation
Once the development server is running:
- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI Schema: `/api/schema/`

## Running Tests
```bash
python manage.py check
python manage.py test
```

## Development Roadmap

### Phase 1 — Foundation
- Project setup, environment, Django, DRF, database configuration, Git, health API and initial tests.
- Custom user, registration, JWT, refresh rotation, logout, password reset, email verification and account deactivation.
- Permissions, object-level access, throttling, validation, CORS, CSRF and Redis fundamentals.

### Phase 2 — Business Logic
- AWS RDS PostgreSQL, networking, migrations, constraints, connections and backups.
- Products, categories, suppliers, SKUs, units, CRUD, search, filtering, pagination and API versioning.
- Warehouses, stock ledger, stock-in/out, transfers, reconciliation, transactions and concurrency.
- Customers, orders, reservations, cancellation, partial fulfilment, expiry, idempotency and order history.

### Phase 3 — Asynchronous Processing
- AWS ElastiCache, Redis caching, invalidation, stampede prevention and failure handling.
- Celery background jobs, reports, scheduling, retries, monitoring and overlapping-job prevention.

### Phase 4 — APIs and User Interface
- Private AWS S3 storage, uploads, IAM and presigned URLs.
- Analytics APIs, revenue metrics, ORM aggregation and query optimization.
- React dashboard with authentication, role-aware access, tables, charts and API error handling.
- WebSockets for real-time updates and webhooks with signatures, replay protection and idempotency.

### Phase 5 — Integrations and Reliability
- Supplier, shipping and notification APIs with authentication, timeouts, retries and rate limits.
- CloudWatch monitoring, structured logs, request IDs, metrics, alarms and incident runbooks.
- Automated, security, load and concurrency testing, query profiling and database recovery drills.

### Phase 6 — Modern Development and Deployment
- AI-assisted development, code review, test generation, Docker, WSL2 and Linux fundamentals.
- AWS production infrastructure: EC2/ECS, ECR, ALB, HTTPS, DNS, IAM, Secrets Manager/SSM and a permission-aware inventory assistant.
- GitHub Actions CI/CD, automated checks, staging, production, AWS OIDC, deployment approvals, health checks and rollback.

## Current Implementation Status
| Phase                                       | Status                                                            |
|---------------------------------------------|-------------------------------------------------------------------|
| Phase 1 — Foundation                        | Completed                                                         |
| Phase 2 — Business Logic                    | Core application implemented; AWS RDS pending                     |
| Phase 3 — Asynchronous Processing           | Redis and Celery configuration implemented; live services pending |
| Phase 4 — APIs and User Interface           | Planned                                                           |
| Phase 5 — Integrations and Reliability      | Planned                                                           |
| Phase 6 — Modern Development and Deployment | Planned                                                           |

## Development Notes
- SQLite is currently used for local development.
- Redis and Celery are configured, but a live Redis server and Celery worker have not been deployed or verified.
- PostgreSQL on AWS RDS and production deployment are planned.
- Roadmap items represent planned learning and development work, not completed functionality.