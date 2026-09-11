# KonnectCore Architecture

## Current scope

The repository is a Django modular monolith. Stages 1–3 implement authentication, organisation workspaces, role-based staff access, controlled onboarding, the tenant boundary, member management, and hierarchical organisation structure. Farms and later operational modules have not been started.

## Modules

- `apps.accounts`: custom user model using a unique email address as the login identifier.
- `apps.organisations`: organisations, account status, user memberships, roles, invitations, active-organisation middleware, onboarding views, and role decorators.
- `apps.members`: organisation-owned members, private documents/photos, audit history, search/filtering, and transactional CSV/XLSX import.
- `apps.groups`: self-referencing Regions, Districts, Branches, Communities, and Groups with tenant-safe leaders, Field Officers, and member assignments.
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
- `StructureUnit`: UUID-addressed hierarchical unit with an optional parent, member leader, and active Field Officer membership.
- `GroupMemberAssignment`: organisation-owned many-to-many assignment between a structure unit and member, with optional join date.

## Onboarding

There is no public registration route. A KonnectCore Super Admin creates an organisation and receives a secure first-Admin invitation URL. Once accepted, that organisation Admin can directly create or invite Managers and Field Officers.

Invitation tokens are shown only when created, stored only as SHA-256 hashes, expire after seven days, and cannot be reused.

## Database and files

PostgreSQL is the default database. Docker stores its data in the named `postgres_data` volume. SQLite is supported only as an explicit local/testing convenience through `DB_ENGINE=sqlite`.

Development uploads will be stored under `media/`, excluded from Git. Django's storage API allows replacement with private S3-compatible storage later.

## Extension guidance

Every business model introduced in later stages must inherit or reproduce the organisation ownership contract, carry a non-null organisation foreign key, validate cross-model organisation consistency, and be queried from `request.organisation`. Add adversarial cross-tenant tests before considering each module complete.

## Farms and crops (Stage 4)

`apps.farms` owns three organisation-scoped models:

- `Crop`: an organisation-specific crop and optional variety catalogue.
- `Farm`: a named member farm with optional size, location, paired GPS coordinates, and notes.
- `FarmCropSeason`: a crop planted on a farm for a named season or planting period, with optional planting dates and estimated/actual yield.

A member may have multiple farms. A farm may have multiple crop-season records. Crops are protected from deletion while referenced. Admins and Managers maintain this data; Field Officers have read access until Stage 7 introduces assigned-member field workflows. Farm history is visible from both the farm screen and member profile.

All forms receive the active organisation explicitly. Member and crop choices are tenant-scoped, every route resolves objects through `.for_organisation(request.organisation)`, and models validate relationship ownership. GPS values must be supplied as a valid latitude/longitude pair; farm sizes and yields cannot be negative; planting end cannot precede planting start.
## Produce collections (Stage 5)

`apps.collections` owns `CollectionRecord`, an organisation-scoped record linking a member and crop to a collection date, location, quantity/unit, quality grade, unit price, calculated total value, optional photo, notes, and the staff user who originally recorded it.

The model calculates `total_value = quantity × price_per_unit` with decimal arithmetic and currency precision on every save. The original recorder is server-controlled and remains unchanged when another authorised staff member edits the record. Admins and Managers may create and edit collections; Field Officers have read access until Stage 7 adds their assigned-member field workflow.

Collection photos are stored below the organisation media namespace and are served only through authenticated, tenant-scoped views. Collection history appears on the already tenant-scoped member profile. Filters support member, crop, date range, location, grade, membership number, and member name; report export remains Stage 8.
## Finance (Stage 6)

`apps.finance` stores tenant-scoped payments to members, dues, contributions, optional savings, and organisation expenses. It is an operational register, not double-entry accounting. Amount, paid amount, status, method, date, reference, notes, and original recorder are retained. Outstanding value is derived from amount less paid amount, with cancelled records excluded.

## Field workspace (Stage 7)

`apps.field` provides a mobile-first workspace. Field Officer member scope is derived from active structure units assigned to that officer; member UUIDs outside that scope return 404. Officers can register members, update assigned-member farms, record visits with notes/GPS/photos, and record collections. Admins and Managers may inspect the field member list but cannot use officer-only mutation routes.
