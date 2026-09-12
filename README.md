# KonnectCore

KonnectCore is a multi-organisation SaaS platform for cooperatives, farmer organisations, associations, and similar member-based organisations.

The validation MVP is complete. It provides private organisation workspaces, role-based staff access, operational records, reporting, a mobile Field Officer experience, and a separate KonnectCore Super Admin area.

## Current MVP scope

1. **Authentication and tenancy** — email login, private workspaces, controlled onboarding, roles, invitations, and organisation status controls.
2. **Members** — profiles, search, status, private photos/documents, CSV/XLSX import, and member history.
3. **Groups and structure** — Regions, Districts, Branches, Communities, Groups, leaders, responsible officers, and member assignments.
4. **Farms and crops** — crop catalogue, farm size/location/GPS, planting periods, seasons, and estimated/actual yields.
5. **Collections** — produce quantities, grades, prices, calculated values, photos, notes, and recorder attribution.
6. **Finance** — member payments, dues, contributions, savings, expenses, methods, statuses, references, and outstanding values.
7. **Field Workspace** — assigned-member search, registration, farm updates, field visits, GPS/photos, and produce entry.
8. **Dashboard and reports** — organisation metrics, operational summaries, filters, and CSV/XLSX exports.
9. **Platform administration** — owner-only organisation list, account details, counts, provisioning, and status management.

## Roles and landing pages

| Account type | Landing page | Main access |
| --- | --- | --- |
| KonnectCore Super Admin | Platform Organisations | Provision and manage organisation accounts |
| Organisation Admin | Organisation Dashboard | Full operational access and staff administration |
| Manager | Organisation Dashboard | Operational management without staff administration |
| Field Officer | Field Workspace | Assigned-member mobile workflows |

There is no public registration. A KonnectCore Super Admin creates a workspace and issues its first Admin invitation. Organisation Admins can then create or invite Managers and Field Officers.

## User interface

The interface uses a consistent green KonnectCore design system with:

- Responsive authenticated application shell and sidebar navigation
- Operational dashboard with compact metrics, tables, summaries, and empty states
- Consistent typography, forms, buttons, filters, tables, and status badges
- Responsive desktop, tablet, and mobile layouts
- Simplified Field Officer navigation with large mobile actions
- Polished login and platform-administration surfaces

Django templates provide the interface; shared presentation rules live in `static/css/app.css`.

## Requirements

### Docker development (recommended)

- Docker Desktop
- Docker Compose

### Local development

- Python 3.12+
- PostgreSQL 17+

## Run with Docker

```powershell
Copy-Item .env.example .env
```

Set secure values for `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` in `.env`, then run:

```powershell
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

Open <http://localhost:8000/login/>.

The web service applies migrations before starting Django. PostgreSQL data is stored in the Docker volume `postgres_data`. Development uploads are stored under `media/` and excluded from Git.

Useful commands:

```powershell
docker compose ps
docker compose logs -f web
docker compose down
```

Do not use `docker compose down -v` unless deleting the PostgreSQL volume is intentional.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `POSTGRES_HOST=localhost`, create the configured PostgreSQL database, and run:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

SQLite is supported only as an explicit development/testing convenience:

```powershell
$env:DB_ENGINE = "sqlite"
python manage.py migrate
python manage.py runserver
```

## Demo data

Populate an existing active organisation with realistic, linked validation data:

```powershell
docker compose exec web python manage.py seed_demo_data --organisation <organisation-slug>
```

To assign a password only to newly created demo staff accounts:

```powershell
docker compose exec web python manage.py seed_demo_data `
  --organisation <organisation-slug> `
  --staff-password '<temporary-password>'
```

The command is transactional, organisation-scoped, and idempotent. Re-running it does not duplicate its deterministic demo records. Never commit real or temporary passwords.

The standard dataset includes 24 members, four groups, four crops, 24 farms/seasons, 34 collections, 31 financial records, 12 visits, and representative Admin/Manager/Field Officer memberships.

See [`docs/demo-and-validation.md`](docs/demo-and-validation.md) for details.

## Tests and verification

Fast SQLite suite:

```powershell
docker compose exec -e DB_ENGINE=sqlite web python -m pytest -q
```

PostgreSQL suite:

```powershell
docker compose run --rm web python -m pytest -q
```

Additional checks:

```powershell
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
```

The current verified baseline contains 103 tests covering authentication, role routing, tenant isolation, permissions, imports, files, operational workflows, exports, dashboard behavior, platform administration, and demo-data idempotency.

## Project organisation

```text
apps/accounts/          Custom email-based user identity
apps/organisations/     Workspaces, memberships, roles, invitations, middleware, onboarding
apps/members/           Members, private files, imports, history
apps/groups/            Hierarchy, groups, leaders, officers, assignments
apps/farms/             Crops, farms, GPS, seasons, yields
apps/collections/       Produce collection records and protected photos
apps/finance/           Payments, dues, contributions, savings, expenses
apps/field/             Assigned-member mobile workflows and visits
apps/reports/           Dashboard, reports, filters, CSV/XLSX exports
apps/core/              Shared foundation and demo-data command
config/                 Settings, routes, WSGI, ASGI
templates/              Server-rendered product interface
static/css/app.css       Shared KonnectCore design system
docs/                   Architecture, tenancy, and validation guidance
```

Read [`docs/architecture.md`](docs/architecture.md) and [`docs/tenancy-and-permissions.md`](docs/tenancy-and-permissions.md) before extending the system.
