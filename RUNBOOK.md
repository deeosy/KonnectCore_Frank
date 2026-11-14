# KonnectCore runbook — run, test, deploy

Copy-ready commands for local development, testing, and the production server.

> **Secrets policy:** this file is committed to Git. Never put real passwords, secret keys, server addresses, or domain logins in it. Fill secrets only into `.env` on your machine or the server.

**Conventions used below**

- Local project folder: the repo root (the folder containing `manage.py`).
- Local site: <http://localhost:8000>
- Docker Compose project folder name here is `KonnectCore_Frank`, so containers are `konnectcore_frank-web-1` and `konnectcore_frank-db-1`. Always prefer `docker compose exec ...`, which works regardless of the folder name.
- Production stack file: `compose.prod.yaml`
- Every fenced block below has a copy button in VS Code, GitHub, and most Markdown viewers.

---

## 0. Quick start (copy-paste, first run)

Run these in order, from the repo root, in PowerShell.

```powershell
Copy-Item .env.example .env
```

Then open `.env` and set a strong `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` (50+ characters for the key; avoid `$` and backticks, Docker Compose interpolates them). Save, then:

```powershell
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

Open the site:

```powershell
Start-Process "http://localhost:8000/login/"
```

---

## 1. Local development with Docker (recommended)

### First-time setup

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```dotenv
DJANGO_SECRET_KEY=<long-random-value-50-chars-or-more>
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
POSTGRES_DB=konnectcore
POSTGRES_USER=konnectcore
POSTGRES_PASSWORD=<strong-local-password>
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

Generate a safe secret and password in PowerShell (prints values you can paste into `.env`):

```powershell
$chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#%^&*-_=+'
-join (1..64 | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
-join (1..32 | ForEach-Object { 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'[(Get-Random -Maximum 62)] })
```

Build and start (migrations run automatically before Django starts):

```powershell
docker compose up --build -d
```

Create the Super Admin (platform owner) account:

```powershell
docker compose exec web python manage.py createsuperuser
```

### Daily use

```powershell
docker compose up -d
```

```powershell
docker compose ps
```

```powershell
docker compose logs -f web
```

```powershell
docker compose down
```

> `docker compose down` keeps the database volume. **Never** run `docker compose down -v` unless you intend to delete all local data.

### Rebuild after dependency or Dockerfile changes

```powershell
docker compose up -d --build
```

### Reset the local database completely (destructive)

```powershell
docker compose down -v
docker compose up -d --build
```

---

## 2. Local development without Docker

Requires Python 3.12+ and (for the default engine) PostgreSQL 17+.

### Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `POSTGRES_HOST=localhost` in `.env`, create the database, then:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### SQLite shortcut (no PostgreSQL needed)

```powershell
$env:DB_ENGINE = "sqlite"
python manage.py migrate
python manage.py runserver
```

SQLite is for development and tests only, not production.

---

## 3. Preview in the browser

Start the stack, then open:

```powershell
Start-Process "http://localhost:8000/login/"
```

Or open <http://localhost:8000/login/> manually. Unauthenticated visits to `/` redirect to the login page.

| Account type | Lands on |
| --- | --- |
| KonnectCore Super Admin | `/platform/organisations/` |
| Organisation Admin | Organisation Dashboard (`/workspace/`) |
| Manager | Organisation Dashboard (`/workspace/`) |
| Field Officer | Field Workspace (`/field/`) |

There is no public registration. A Super Admin creates the organisation and issues the first Admin invitation.

### Local demo login accounts

> **Local development only.** These accounts exist only in your local database. Never create or reuse these passwords on the production server, and rotate/delete them before any shared or public deployment. If this repo is ever made public or access is widened, treat these passwords as compromised.

| Role | Email | Password | Lands on |
| --- | --- | --- | --- |
| KonnectCore Super Admin | `admin@konnectcore.local` | `KonnectCore2026!` | `/platform/organisations/` |
| Organisation Admin | `owner@greenfields.local` | `KonnectCore2026!` | `/workspace/` |
| Manager | `manager@demo.konnectcore.local` | `DemoStaff2026!` | `/workspace/` |
| Field Officer (North) | `field.north@demo.konnectcore.local` | `DemoStaff2026!` | `/field/` |
| Field Officer (South) | `field.south@demo.konnectcore.local` | `DemoStaff2026!` | `/field/` |

Login page: <http://localhost:8000/login/>

**If these accounts do not exist** (fresh clone, reset database, or different machine), recreate them. This creates the Super Admin, an active organisation (`greenfields`), and its Admin, then seeds the demo dataset with the staff passwords above:

```powershell
@'
from django.contrib.auth import get_user_model
from apps.organisations.models import Organisation, OrganisationMembership

User = get_user_model()

admin, _ = User.objects.get_or_create(
    email="admin@konnectcore.local",
    defaults={"first_name": "Platform", "last_name": "Admin", "is_staff": True, "is_superuser": True},
)
admin.is_staff = admin.is_superuser = True
admin.set_password("KonnectCore2026!")
admin.save()

org, _ = Organisation.objects.get_or_create(
    slug="greenfields",
    defaults={"name": "Greenfields Cooperative", "currency": "GHS", "status": "active"},
)
owner, _ = User.objects.get_or_create(
    email="owner@greenfields.local",
    defaults={"first_name": "Ama", "last_name": "Owusu"},
)
owner.set_password("KonnectCore2026!")
owner.save()
OrganisationMembership.objects.update_or_create(
    organisation=org, user=owner,
    defaults={"role": "admin", "is_active": True},
)
'@ | docker compose exec -T web python manage.py shell
```

```powershell
docker compose exec web python manage.py seed_demo_data --organisation greenfields --staff-password 'DemoStaff2026!'
```

Change any of these later with:

```powershell
docker compose exec web python manage.py changepassword admin@konnectcore.local
```

### Load demo data into a workspace

The organisation must already exist, be active, and have an active Admin.

```powershell
docker compose exec web python manage.py seed_demo_data --organisation <organisation-slug>
```

Give newly created demo staff a password (only applied to accounts it creates):

```powershell
docker compose exec web python manage.py seed_demo_data --organisation <organisation-slug> --staff-password '<temporary-password>'
```

Demo dataset: 24 members, 4 groups, 4 crops, 24 farms/seasons, 34 collections, 31 financial records, 12 visits. Re-running is idempotent.

---

## 4. Tests

### Fast suite (SQLite inside the running container)

```powershell
docker compose exec -e DB_ENGINE=sqlite web python -m pytest -q
```

### Full suite (PostgreSQL, dedicated container)

```powershell
docker compose run --rm web python -m pytest -q
```

### Run one app or one file

```powershell
docker compose exec -e DB_ENGINE=sqlite web python -m pytest apps/organisations -q
```

```powershell
docker compose exec -e DB_ENGINE=sqlite web python -m pytest apps/organisations/tests.py -q
```

### Run one test

```powershell
docker compose exec -e DB_ENGINE=sqlite web python -m pytest "apps/organisations/tests.py::<TestClass>::<test_name>" -q
```

### Django system checks

```powershell
docker compose exec web python manage.py check
```

```powershell
docker compose exec web python manage.py makemigrations --check --dry-run
```

### Test notes

- Run **one** test run at a time. Parallel runs share the test database and fail.
- On a PC without the web container running, use `$env:DB_ENGINE = "sqlite"` before `python -m pytest -q`, otherwise it waits for PostgreSQL.
- Current baseline verified locally: **332 tests pass** (PostgreSQL). Treat failures as regressions.
- The production image runs the same code; run the PostgreSQL suite before a release.

---

## 5. Useful management commands

Open a Django shell:

```powershell
docker compose exec web python manage.py shell
```

Apply migrations:

```powershell
docker compose exec web python manage.py migrate
```

Create an organisation + first Admin from the platform UI (Super Admin): `/platform/organisations/create/`.

Change a password interactively:

```powershell
docker compose exec web python manage.py changepassword <email>
```

Check deployed settings (no secrets printed):

```powershell
docker compose exec web python manage.py diffsettings
```

---

## 6. Production (server)

The production stack is `compose.prod.yaml`: `caddy` (HTTPS, ports 80/443), `web` (Gunicorn), `db` (PostgreSQL 17). Only Caddy exposes ports. `web` runs `migrate` and `collectstatic` before Gunicorn; if `collectstatic` fails the container does not start.

### Server `.env` requirements

Create `/path/to/app/.env` on the server (root-only permissions, never committed) with at least:

```dotenv
DJANGO_SECRET_KEY=<50+ random characters>
DJANGO_ALLOWED_HOSTS=<your-domain>
DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-domain>
KC_DOMAIN=<your-domain>
POSTGRES_DB=konnectcore
POSTGRES_USER=konnectcore
POSTGRES_PASSWORD=<strong-password>
```

Do **not** set `DJANGO_DEBUG=true` on the server. `compose.prod.yaml` sets `DJANGO_DEBUG=false` and `DJANGO_SECURE=true`, which enables HTTPS redirect, secure cookies, HSTS, and hashed static filenames. Startup fails if the secret key is weak or CSRF trusted origins are missing.

Lock down the file:

```bash
chmod 600 .env
```

### First production start

```bash
docker compose -f compose.prod.yaml up -d --build
```

Create the Super Admin:

```bash
docker compose -f compose.prod.yaml exec web python manage.py createsuperuser
```

### Deploy a new release (code already extracted into the app folder)

```bash
docker compose -f compose.prod.yaml up -d --build web
```

Only `web` is rebuilt; database and Caddy stay up.

### Status and logs

```bash
docker compose -f compose.prod.yaml ps
```

```bash
docker compose -f compose.prod.yaml logs -f web
```

```bash
docker compose -f compose.prod.yaml logs -f caddy
```

### Verify after deploy

```bash
curl -I https://<your-domain>/login/
```

```bash
curl -s -o /dev/null -w "django-admin: %{http_code}\n" https://<your-domain>/django-admin/
```

```bash
curl -s -o /dev/null -w "media: %{http_code}\n" https://<your-domain>/media/
```

Expected: login page `200`; `/django-admin/` and `/media/` `404`. Check that the hashed CSS/JS referenced by the page loads, and that the response has `Strict-Transport-Security`, `X-Content-Type-Options`, and `Referrer-Policy`.

### Rollback

Extract the previous release package into the app folder, update the `RELEASE` file, then:

```bash
docker compose -f compose.prod.yaml up -d --build web
```

If the previous release had no migrations, code rollback alone is enough. Otherwise restore the matching database backup as well.

### Backups before any deploy

Do not deploy without a fresh, checksum-verified backup of the database and uploaded files. Backups live on the server and in the owner's private copy; never commit them.

### Build a release package (from the repo root on your PC)

```powershell
git archive --format=tar.gz -o konnectcore-release.tar.gz HEAD
```

Use `-o`; piping through PowerShell corrupts the archive. Compare the SHA-256 on both ends before extracting on the server.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `The "r" variable is not set` / mangled secret | `$` inside `.env` | Regenerate secrets without `$` or backticks |
| Django `ImproperlyConfigured` on the server | Missing/weak `DJANGO_SECRET_KEY`, missing `DJANGO_CSRF_TRUSTED_ORIGINS`, or debug on with `DJANGO_SECURE=true` | Fix `.env`, then `docker compose -f compose.prod.yaml up -d --build web` |
| Postgres auth failure after changing `POSTGRES_PASSWORD` locally | Volume was initialised with the old password | `docker compose down -v` then `up -d --build` (destroys local data) |
| Port 8000 already in use locally | Another server is running | Stop it, or change the `ports` mapping in `compose.yaml` |
| `Invalid HTTP_HOST header` in tests | Test client host not allowed | Use `Client(SERVER_NAME="localhost")` |
| CSS changes not showing in production | Hashed static filenames | Rebuild `web` so `collectstatic` re-runs; never serve `static/` directly |
| Browser shows old page while signed in | `Cache-Control: no-store` expected; real cause is service worker/proxy | Hard-refresh, check Caddy/DNS |

---

## 8. Copy-paste cheat sheet

### Local: start, preview, stop

```powershell
docker compose up -d
docker compose ps
docker compose logs -f web
docker compose down
```

### Local: rebuild

```powershell
docker compose up -d --build
```

### Local: tests + checks

```powershell
docker compose exec -e DB_ENGINE=sqlite web python -m pytest -q
docker compose run --rm web python -m pytest -q
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
```

### Local: demo data

```powershell
docker compose exec web python manage.py seed_demo_data --organisation <organisation-slug>
```

### Production: deploy and verify (bash on the server)

```bash
docker compose -f compose.prod.yaml up -d --build web
docker compose -f compose.prod.yaml ps
docker compose -f compose.prod.yaml logs --tail 100 web
curl -I https://<your-domain>/login/
```
