# Demo Data and Validation

## Purpose

The demo dataset gives product reviewers a realistic view of KonnectCore without changing production models or bypassing tenant isolation.

## Populate a workspace

The target organisation must already exist, be active, and have an active Admin membership.

```powershell
docker compose exec web python manage.py seed_demo_data --organisation <organisation-slug>
```

New demo staff accounts receive unusable passwords unless a temporary password is explicitly supplied:

```powershell
docker compose exec web python manage.py seed_demo_data `
  --organisation <organisation-slug> `
  --staff-password '<temporary-password>'
```

Do not store passwords in source files, documentation, commits, or issue trackers.

## Dataset

The standard seed creates or reuses:

- One Manager and two Field Officer memberships
- 24 members with mixed active/inactive/suspended statuses
- Region and District hierarchy with four Groups
- 24 member-to-group assignments
- Four crops
- 24 farms with GPS coordinates
- 24 crop-season profiles
- 34 produce collections
- 31 finance records across all supported record types
- 12 field visits
- Member creation history without internal seed metadata in the UI

## Safety properties

- Requires an explicit organisation slug
- Refuses inactive organisations
- Requires an existing active organisation Admin
- Runs in one database transaction
- Uses deterministic natural keys
- Is idempotent across reruns
- Does not create schema changes
- Does not create public files or photos
- Does not touch other organisations

## Validation checklist

After seeding:

```powershell
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec -e DB_ENGINE=sqlite web python -m pytest -q
docker compose run --rm web python -m pytest -q
```

Verify actual password login behavior rather than relying only on test-client `force_login`:

- Super Admin lands in Platform Organisations.
- Admin lands on the Organisation Dashboard and sees Staff / Settings.
- Manager lands on the Organisation Dashboard without staff administration.
- Field Officers land in the assigned-member Field Workspace with simplified navigation.

## Resetting data

The command intentionally has no destructive reset option. Remove or replace demo records only through an explicit, reviewed maintenance operation scoped to the intended organisation. Never delete the PostgreSQL volume merely to refresh one tenant.
