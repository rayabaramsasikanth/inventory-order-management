# Inventory & Order Management System

A Django REST Framework API for managing suppliers, products, warehouses, inventory, stock movements and customer orders.

## 1. Project Overview

The Inventory & Order Management System provides backend APIs for businesses that purchase products from suppliers, store them in warehouses, manage stock and process customer orders.

The system focuses on inventory accuracy, stock tracking, order processing, authentication and business operations.

### Business Workflow

**Supplier → Product → Warehouse → Inventory → Customer → Order → Stock Reservation → Order Fulfilment**

## 2. Key Features

### Authentication and Security
- Custom user model
- User registration and login
- JWT access and refresh tokens
- Refresh token rotation and blacklisting
- Logout and password management
- Email verification and password reset
- Role-based permissions
- API throttling and input validation

### Product and Supplier Management
- Category management
- Product management
- SKU validation and normalization
- Unit of measurement management
- Supplier management
- Product search and filtering
- Pagination and API versioning

### Warehouse and Inventory Management
- Warehouse management
- Warehouse staff assignments
- Inventory tracking
- Stock-in and stock-out operations
- Stock adjustments
- Stock transfers
- Stock reconciliation
- Inventory transaction history

### Order Management
- Customer management
- Order creation and management
- Order items
- Stock reservation
- Order cancellation
- Order status history
- Pending order expiry
- Idempotency support

### API and Background Processing
- REST API endpoints
- Swagger and ReDoc documentation
- OpenAPI schema
- Redis cache configuration
- Celery task configuration
- Scheduled background task definitions
- Health-check endpoint

## 3. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming |
| Django | Web framework |
| Django REST Framework | REST API development |
| SimpleJWT | JWT authentication |
| SQLite | Local development database |
| PostgreSQL | Planned AWS RDS database |
| django-filter | API filtering |
| drf-spectacular | API documentation |
| Redis | Caching and Celery broker configuration |
| Celery | Background task processing |
| Git | Version control |
| GitHub | Source code management |
| AWS | Planned cloud infrastructure |
| Docker | Planned containerization |

## 4. Project Structure

```text
inventory-order-management/
│
├── apps/
│   ├── catalog/
│   │   ├── migrations/
│   │   └── tests/
│   │
│   └── core/
│       ├── management/
│       └── migrations/
│
├── config/
├── .env.example
├── .gitignore
├── manage.py
├── requirements.txt
└── README.md
```

Application folders may contain their own models, serializers, views, URLs, permissions, services, tasks and tests.

## 5. Local Installation and Setup

### Prerequisites

- Python
- Git
- Visual Studio Code or another code editor

### Clone the repository

```bash
git clone https://github.com/rayabaramsasikanth/inventory-order-management.git
cd inventory-order-management
```

### Create a virtual environment

```bash
python -m venv .venv
```

Activate it in Git Bash:

```bash
source .venv/Scripts/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure environment variables

Create a local `.env` file using `.env.example` as a reference.

Configure the required Django secret key, debug setting, email settings and other environment-specific values.

Do not commit `.env` or production credentials to GitHub.

### Apply migrations

```bash
python manage.py migrate
```

### Create a superuser

```bash
python manage.py createsuperuser
```

### Start the development server

```bash
python manage.py runserver
```

The local API server runs at:

`http://127.0.0.1:8000/`

## 6. API Documentation

After starting the development server, access:

| Documentation | Endpoint |
|---|---|
| Swagger UI | `/api/docs/` |
| ReDoc | `/api/redoc/` |
| OpenAPI Schema | `/api/schema/` |

The API documentation describes available endpoints, request parameters, request bodies and responses.

## 7. Filtering, Searching and Pagination

The API supports filtering and searching on applicable list endpoints.

Common query parameter examples:

```text
?search=keyboard
?ordering=name
?page=2
?page_size=20
```

Available fields and supported filters depend on the individual API endpoint. Refer to Swagger documentation for the exact parameters.

## 8. Running Tests

Run Django system checks:

```bash
python manage.py check
```

Run the complete test suite:

```bash
python manage.py test
```

Run tests for an individual application:

```bash
python manage.py test apps.catalog
```

### Latest Recorded Test Status

- 172 tests passed.
- 1 PostgreSQL-specific test skipped when running against SQLite.
- Django system check passed.

These are the latest recorded results, not a guarantee that every test passes after future changes.

## 9. Git Branching Strategy

The project follows a branch-based development workflow.

| Branch | Purpose |
|---|---|
| `main` | Stable, release-ready code |
| `develop` | Integration branch |
| `feature/*` | New features |
| `bugfix/*` | Bug fixes |
| `release/*` | Release preparation |
| `hotfix/*` | Urgent production fixes |

Temporary branches are created when required and merged through pull requests.

### Development Workflow

1. Start from the `develop` branch.
2. Create a feature or bugfix branch.
3. Implement the assigned task.
4. Write and run automated tests.
5. Commit and push the changes.
6. Create a pull request targeting `develop`.
7. Complete code review and testing.
8. Merge approved changes.
9. Prepare releases from `develop` and merge approved releases into `main`.

## 10. Development Roadmap

### Phase 1 — Foundation

- Project setup and configuration
- Authentication and JWT
- Password management and email verification
- Roles and permissions
- API security and validation
- Health endpoint and automated tests

### Phase 2 — Business Logic

- Database infrastructure using AWS RDS PostgreSQL
- Products, suppliers and categories
- Warehouse and inventory management
- Stock movements and reconciliation
- Customers and order management
- Stock reservation and order fulfilment

### Phase 3 — Asynchronous Processing

- Redis caching
- Celery background tasks
- Scheduled jobs
- Low-stock reports
- Order and revenue reports
- Task retries and failure handling

### Phase 4 — APIs and User Interface

- AWS S3 file storage
- Analytics APIs
- React dashboard
- WebSockets and real-time updates
- Webhook integrations

### Phase 5 — Integrations and Reliability

- External API integrations
- Monitoring and logging
- Automated and performance testing
- Security checks
- Backup and recovery procedures

### Phase 6 — Deployment and Modern Development

- Docker containerization
- AWS deployment using EC2 or ECS
- Amazon ECR
- GitHub Actions CI/CD
- Infrastructure automation
- Production monitoring
- AI-assisted development and inventory assistant

## 11. Current Implementation Status

| Area | Status |
|---|---|
| Django and DRF foundation | Implemented |
| Authentication and permissions | Implemented |
| Product and supplier APIs | Implemented |
| Warehouse and inventory APIs | Implemented |
| Order management | Implemented |
| Search, filtering and pagination | Implemented |
| API versioning and documentation | Implemented |
| Redis integration configuration | Implemented |
| Celery task configuration | Implemented |
| Local automated tests | Previously passed |
| AWS RDS PostgreSQL | Pending |
| Live Redis service | Pending verification |
| Live Celery worker and scheduler | Pending verification |
| S3 integration | Planned |
| React dashboard | Planned |
| WebSockets | Planned |
| Docker deployment | Planned |
| AWS production deployment | Planned |
| GitHub Actions CI/CD | Planned |

**Note:** Implemented application code does not necessarily mean that the corresponding external infrastructure or production service is deployed and running.

## 12. Development Notes

- SQLite is currently used for local development.
- PostgreSQL on AWS RDS is planned.
- Redis and Celery configurations are present, but live service operation must be verified.
- Production deployment and cloud infrastructure are not yet completed.
- Environment variables and sensitive credentials must remain outside source control.

## 13. Repository

GitHub: https://github.com/rayabaramsasikanth/inventory-order-management

---

**Project:** Inventory & Order Management System

**Backend:** Python, Django and Django REST Framework

**Version Control:** Git and GitHub