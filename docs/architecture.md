# KonnectCore Architecture

## System shape

KonnectCore is a Django modular monolith backed by PostgreSQL. It uses server-rendered templates and a shared responsive CSS design system. This structure keeps the validation MVP straightforward to deploy and maintain while preserving clear module boundaries.

The nine planned MVP stages are complete.

## Modules

- `apps.accounts`: custom user model with a unique email login identifier.
- `apps.organisations`: organisations, account statuses, memberships, roles, invitations, tenant middleware, role-aware login, onboarding, and platform administration.
- `apps.members`: organisation-owned members, private files, history, search/filtering, and transactional CSV/XLSX import.
- `apps.groups`: hierarchical structure units, leaders, responsible Field Officers, and member assignments.
- `apps.farms`: organisation crop catalogue, farms, GPS, crop seasons, planting periods, and yields.
- `apps.collections`: produce collection records, calculated values, private photos, and recorder attribution.
- `apps.finance`: payments, dues, contributions, savings, and basic organisation expenses.
- `apps.field`: assigned-member Field Officer workflows and field visits.
- `apps.reports`: dashboard metrics, reports, filters, and CSV/XLSX exports.
- `apps.core`: shared application foundation and the idempotent demo-data management command.
- `config`: environment-driven settings and root routing.
- `templates` and `static`: shared responsive product interface and design system.

## Authentication and request flow

1. Django authenticates users by email and password.
2. The role-aware login view chooses the correct destination:
   - Super Admin → platform organisation list
   - Admin/Manager → organisation dashboard
   - Field Officer → Field Workspace
3. `ActiveOrganisationMiddleware` resolves the selected organisation only from an authenticated, active membership in an active organisation.
4. Users with one valid membership are assigned that organisation automatically. Users with multiple memberships choose one.
5. Protected views apply `organisation_required` or a server-side role decorator.
6. Tenant-owned queries start from `request.organisation`; client-supplied organisation identifiers are never trusted.

Field Officers are also redirected at the dashboard boundary, so manually opening a dashboard URL does not bypass their simplified workspace.

## Tenancy model

KonnectCore uses a shared PostgreSQL database with organisation-scoped rows. Tenant-owned models inherit `OrganisationOwnedModel`, and `OrganisationQuerySet.for_organisation()` fails closed when no valid organisation is supplied.

Every operational relationship is validated within one organisation. Lists, details, searches, files, metrics, reports, and exports resolve data from the active organisation. Cross-tenant UUIDs return 404 or fail validation.

## Principal models

### Identity and tenancy

- `User`
- `Organisation`
- `OrganisationMembership`
- `StaffInvitation`
- `OrganisationOwnedModel`

### Membership and structure

- `Member`
- `MemberDocument`
- `MemberHistory`
- `StructureUnit`
- `GroupMemberAssignment`

### Operations

- `Crop`
- `Farm`
- `FarmCropSeason`
- `CollectionRecord`
- `FinancialRecord`
- `FieldVisit`

## Onboarding

Public registration is disabled. A KonnectCore Super Admin creates an organisation and receives a secure first-Admin invitation URL. The organisation Admin can then directly create or invite Managers and Field Officers.

Invitation tokens are stored only as SHA-256 hashes, expire after seven days, and are single-use. Invitation acceptance also uses role-aware landing behavior.

## Permissions

- **Organisation Admin:** full operational access and staff administration.
- **Manager:** operational management without staff or platform administration.
- **Field Officer:** assigned-member Field Workspace and officer-only field actions.
- **KonnectCore Super Admin:** owner-only platform administration; not an organisation role.

Permissions are enforced by views/decorators and scoped querysets, not merely hidden navigation.

## Operational behavior

### Members

Members use UUID identifiers and organisation-scoped membership numbers. Photos and documents are private and delivered through authenticated tenant-checked views. Create, update, import, and document actions are recorded in member history. CSV/XLSX imports are atomic.

### Groups

Self-referencing `StructureUnit` records support Region, District, Branch, Community, and Group levels. The system rejects hierarchy cycles, invalid responsible officers, duplicate sibling/root names, and cross-organisation relationships.

### Farms and crops

A member can have multiple farms and crop-season records. GPS coordinates are paired and range-validated. Farm sizes and yields cannot be negative, and planting end cannot precede planting start.

### Collections

Collection totals are calculated server-side with decimal arithmetic. The original recorder is server-controlled. Photos remain private and collection history appears on the member profile.

### Finance

Finance is a simple operational register rather than a full accounting system. It supports member payments, dues, contributions, savings, and organisation expenses.

#### Meaning of FinancialRecord fields

| Field | Meaning |
| --- | --- |
| `amount` | The total owed or scheduled for this record. It is not money that has moved. |
| `paid_amount` | Money actually paid so far. Always between 0 and `amount`. |
| `status` | Must agree with `paid_amount`: Pending means nothing paid, Part-paid means some but not all, Paid means `paid_amount` equals `amount`. Cancelled means the record no longer counts as owed. |
| Outstanding | Derived: `amount - paid_amount`, or zero when Cancelled. |

Direction: Payment to member and Organisation expense are outgoing; Membership due, Contribution and Savings are incoming. Dashboard and export totals are calculated from these records only, using `paid_amount` for money paid and Outstanding for money still owed. A record with GHS 1,000 `amount` and GHS 400 `paid_amount` counts as GHS 400 paid and GHS 600 owed.

#### Collection settlement (allocations)

Only outgoing Payment to member records can be linked to collections. Dues, contributions and savings are outside this workflow.

- **Purpose.** A Payment to member is either *For collections* (at least one allocation) or *Other* (a written description is required). Records created before allocations existed show *Purpose not recorded* and are unresolved: they are not evidence that any collection is paid or unpaid.
- **Allocated means money actually paid.** Allocation amounts are portions of `paid_amount`, never of `amount`. The sum of a payment's active allocations cannot exceed its `paid_amount`. Scheduled but unpaid money is never allocated.
- **Distribution of partial payments.** Staff enter an explicit amount for each collection. The system never splits a payment automatically and never copies the full payment amount onto each collection.
- **Unallocated balance.** For a *For collections* payment, `paid_amount - allocated` is shown as the unallocated balance on the payment and in the finance list and export, so no paid money is left unexplained.
- **Collection limits.** Same organisation and same member as the payment. The total allocated to a collection from non-cancelled payments cannot exceed its `total_value`. New allocations to voided collections are rejected. A payment allocates to a given collection at most once.
- **Collection figures.** *Value* is `total_value`; *Allocated* is the sum of active allocations from non-cancelled payments; *Value not yet covered by payments* is the difference. It is collection value, not cash; unallocated cash is shown only on the payment as *Unallocated paid balance*. The collection page does not use the word Paid for allocated money.
- **Revalidation.** Editing a payment's `paid_amount` or status, editing an allocation, or editing a collection's quantity or price re-checks these limits. An edit that would break them is rejected with an explanation.
- **Atomic saves.** A payment and its allocations are saved in one transaction with duplicate-submission protection; a failed save leaves neither.
- **Corrections.** Allocations are moved or removed rather than cancelling genuine payments. Removed or moved allocations are kept with who changed them, when and why.
- **Cancelled payments.** Their allocations stop counting towards collection figures and void checks; the history remains.

#### Voiding collections and archiving members

- Only Admins and Managers can void a collection, with a required reason and a confirmation step. Voided collections are excluded from collection totals, reports and exports, and remain visible, struck through, with who voided them and why.
- Voiding is blocked while any non-cancelled payment has an active allocation to the collection. The user is told to move or remove the allocation first; the app does not suggest cancelling the payment.
- If the member has non-cancelled Payment to member records with no recorded purpose, the void screen lists them. The Admin or Manager records a decision (*Not related* or *Related, will link first*) and a reason; *Related* blocks the void. The decision, reason and reviewed payment IDs are stored with the void.
- Archived members are hidden from default lists and the Field Workspace. Their collections, payments and history stay in historical reports and exports.

### Field Workspace

Field Officer scope is derived from active groups assigned to that exact organisation membership. Unassigned or cross-tenant member UUIDs return 404. Officers can register members, update assigned-member farms, record visits, and create collections.

### Dashboard and reports

The dashboard uses tenant-scoped read queries for member, group, farm, collection, payment, outstanding, crop, and activity summaries. Reports support member, group, crop, payment-status, and date filters. Admins and Managers can export CSV/XLSX; Field Officers cannot export.

### Platform administration

Django superusers can list organisations, review user/member counts, create workspaces, inspect memberships, and activate, suspend, or close organisation accounts. Suspended/closed workspaces cannot establish an active tenant context.

## Interface architecture

`templates/base.html` owns the shared authenticated shell and role-aware navigation. Module templates extend it for consistent pages, forms, tables, filters, status badges, and empty states. `static/css/app.css` owns design tokens and responsive behavior.

The Field Officer shell intentionally exposes only the Field Workspace navigation. Admin and Manager share the organisation dashboard but receive different administration capabilities.

## Database and files

PostgreSQL is the default database. Docker stores data in the `postgres_data` volume. SQLite is available only when explicitly selected for local tests/development.

Development uploads live under `media/` and are excluded from Git. Django's storage API allows migration to private S3-compatible storage later.

## Demo and validation data

`python manage.py seed_demo_data --organisation <slug>` creates deterministic linked validation data only in the named active organisation. It requires an existing active organisation Admin, runs transactionally, and can be rerun without duplicating its records.

## Extension guidance

Before adding any module or relationship:

1. Make organisation ownership explicit and non-null where applicable.
2. Resolve all tenant-owned objects through the active organisation.
3. Validate related-object ownership.
4. Enforce roles server-side.
5. Add two-tenant adversarial tests for reads, writes, files, reports, and exports.
6. Verify suspended organisations fail closed.
7. Run both SQLite and PostgreSQL suites and check migration drift.
