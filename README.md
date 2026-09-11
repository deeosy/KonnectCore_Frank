# KonnectCore

KonnectCore is a multi-organisation SaaS platform for cooperatives, farmer organisations, associations, and similar member-based organisations.

This repository currently contains **Stage 1 only**: authentication, private organisation workspaces, staff roles, controlled onboarding, and tenant-isolation foundations.

## Stage 1 features

- Email/password authentication with no public registration
- KonnectCore Super Admin organisation provisioning
- Secure, expiring invitation for an organisation's first Admin
- Organisation Admin creation and invitation of Managers and Field Officers
- Private organisation workspace selection
- Server-side role enforcement
- Active/suspended/closed organisation status
- Responsive desktop, tablet, and mobile interface
- Automated authentication, permission, invitation, and cross-organisation isolation tests

Stage 2 member management has intentionally not been started.

## Requirements

### Docker (recommended)

- Docker Desktop
- Docker Compose

### Local development

- Python 3.12+
- PostgreSQL 17+

## Run with Docker

1. Copy the environment template:

   ```powershell
   Copy-Item .env.example .env
   ```

2. Replace `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` in `.env`.
3. Build and start the application:

   ```powershell
   docker compose up --build
   ```

4. In another terminal, create the first KonnectCore Super Admin:

   ```powershell
   docker compose exec web python manage.py createsuperuser
   ```

5. Open <http://localhost:8000/login/>.

The web container applies database migrations before starting Django. PostgreSQL data is stored in the Docker volume `postgres_data`. Uploaded files will use `media/` during development and are excluded from Git.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `POSTGRES_HOST=localhost` in `.env`, create the configured PostgreSQL database, then run:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

For a temporary SQLite development database only:

```powershell
$env:DB_ENGINE = "sqlite"
python manage.py migrate
python manage.py runserver
```

PostgreSQL remains the production and Docker database.

## Tests

Fast local suite:

```powershell
$env:DB_ENGINE = "sqlite"
python -m pytest
```

PostgreSQL/Docker suite:

```powershell
docker compose run --rm web python -m pytest
```

## Main organisation

```text
apps/accounts/          Custom email-based user model
apps/organisations/     Organisations, memberships, roles, invitations, tenant middleware
apps/core/              Shared application foundation for later stages
config/                 Django settings and URL configuration
templates/              Responsive server-rendered interface
static/                 Shared CSS and future static assets
docs/                   Architecture and tenant-security notes
```

See `docs/architecture.md` and `docs/tenancy-and-permissions.md` before extending the system.
