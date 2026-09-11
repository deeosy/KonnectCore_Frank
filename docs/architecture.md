# KonnectCore Architecture

## Current scope

The repository is a Django modular monolith. Stages 1–2 implement authentication, organisation workspaces, role-based staff access, controlled onboarding, the tenant boundary, and member management. Groups and later operational modules have not been started.

## Modules

- `apps.accounts`: custom user model using a unique email address as the login identifier.
- `apps.organisations`: organisations, account status, user memberships, roles, invitations, active-organisation middleware, onboarding views, and role decorators.
- `apps.members`: organisation-owned members, private documents/photos, audit history, search/filtering, and transactional CSV/XLSX import.
- `apps.core`: reserved for shared abstractions used by later business modules.
- `config`: environment-driven settings, root routes, WSGI, and ASGI configuration.
- `templates` and `static`: responsive server-rendered UI.

## Request flow

1. Django authenticates the user.
2. `ActiveOrganisationMiddleware` reads the selected organisation from the session.
3. The middleware accepts that selection only when the user has an active membership and the organisation is active.
4. Protected organisation views use `organisation_required` or a role decorator.
5. Views use `request.organisation`; organisation identifiers are not trusted from client input for tenant-owned operations.

A user with exactly one valid membership is automatically placed in that workspace. A user with multiple memberships chooses one. Invalid or forged session selections are removed.

## Principal models

- `User`: email-based identity shared by the platform.
- `Organisation`: private workspace with currency and active/suspended/closed status.
- `OrganisationMembership`: unique user-to-organisation relationship with Admin, Manager, or Field Officer role.
- `StaffInvitation`: hashed, seven-day, single-use invitation scoped to one organisation and role.
- `OrganisationOwnedModel`: abstract base for future tenant-owned records.
- `OrganisationQuerySet.for_organisation()`: fail-closed query helper used by tenant-owned records.
- `Member`: UUID-addressed member identity with organisation-scoped membership-number uniqueness.
- `MemberDocument`: private PDF/image attachment stored below the owning organisation/member path.
- `MemberHistory`: actor-attributed create, update, document, and import history.

## Onboarding

There is no public registration route. A KonnectCore Super Admin creates an organisation and receives a secure first-Admin invitation URL. Once accepted, that organisation Admin can directly create or invite Managers and Field Officers.

Invitation tokens are shown only when created, stored only as SHA-256 hashes, expire after seven days, and cannot be reused.

## Database and files

PostgreSQL is the default database. Docker stores its data in the named `postgres_data` volume. SQLite is supported only as an explicit local/testing convenience through `DB_ENGINE=sqlite`.

Development uploads will be stored under `media/`, excluded from Git. Django's storage API allows replacement with private S3-compatible storage later.

## Extension guidance

Every business model introduced in later stages must inherit or reproduce the organisation ownership contract, carry a non-null organisation foreign key, validate cross-model organisation consistency, and be queried from `request.organisation`. Add adversarial cross-tenant tests before considering each module complete.
