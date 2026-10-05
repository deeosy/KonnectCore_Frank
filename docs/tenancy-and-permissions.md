# Tenancy and Permissions

Organisation isolation is a primary security invariant, not a UI feature.

## Tenant boundary

KonnectCore uses one PostgreSQL database with organisation-scoped rows. Every organisation-owned business record must have a required `organisation_id`. The active organisation is established server-side from an authenticated user's active membership.

Never:

- Query an organisation-owned model globally in an organisation view.
- Trust an organisation ID supplied in a URL, form, query string, header, or API body.
- Assign a related object before proving it belongs to `request.organisation`.
- Expose a report, export, file, aggregate, or search result without organisation scope.
- Treat hidden links or disabled buttons as authorization.

Always:

- Start organisation-owned queries with `.for_organisation(request.organisation)` or an equivalent mandatory scope.
- Check related records against the same organisation.
- Enforce authorization server-side with decorators/services.
- Include `organisation` in relevant uniqueness constraints.
- Test object-ID guessing, forged workspace sessions, exports, aggregates, files, create/update/delete operations, and suspended accounts across at least two organisations.

## Roles

- **Admin**: organisation settings and staff administration; full organisation operational access as modules are added.
- **Manager**: operational management but no staff or platform administration.
- **Field Officer**: assigned-member field workflows with a simplified role-specific workspace.
- **KonnectCore Super Admin**: platform owner identity using Django superuser status; not an organisation role.

Stage 1 enforces that only organisation Admins can list, create, or invite staff. Managers and Field Officers receive HTTP 403 for those operations. Organisation users cannot access platform administration.

Stage 2 member access is role-scoped. Admins and Managers can view all tenant-scoped member lists and profiles, register/edit members, attach documents, and import records. Field Officers cannot open the organisation-wide member list or profile; those routes redirect them to the Field Workspace. Field Officers see only their assigned members (see Stage 7 and *Field Officer record scope*). Member detail, edit, file, search, and import operations are all derived from `request.organisation`; cross-tenant UUID guessing returns 404.

> **Policy change (pilot readiness).** Earlier versions of this document allowed all active staff roles, including Field Officers, to view every member list and profile in the organisation. Field Officer reads across the organisation therefore matched the documented policy at that time. Restricting Field Officers to their assigned members is an intentional, approved policy change, not a correction of undocumented behaviour.

Stage 3 structure access: Admins and Managers can view units and assignments, create/edit units, and add/remove members. Field Officers are redirected from the organisation-wide structure list and detail pages to the Field Workspace. Parent units, leaders, responsible Field Officers, and assigned members must all belong to the active organisation. Responsible officers must be active Field Officer memberships. Hierarchy cycles and duplicate sibling/root names are rejected.

## Account status

Only active organisations produce an active tenant context. Suspending or closing an organisation makes its workspace unavailable even when a user's membership remains active.

## Invitations

Invitations are scoped to one organisation, email, and role. Raw tokens are never stored. Tokens expire after seven days and are invalid after acceptance. A pending invitation for the same organisation and email is replaced when reissued.

## Review checklist for every later stage

1. All new tenant-owned tables have required organisation ownership.
2. Every read/write/export/file route derives scope from `request.organisation`.
3. Cross-organisation foreign keys are rejected.
4. Role behavior is covered by request tests.
5. Two-tenant adversarial tests prove no list/detail/search/report/file leakage.
6. Suspended organisations cannot use the module.
7. PostgreSQL migrations and the complete test suite pass.

## Stage 4 farm and crop controls

- Crop, Farm, and FarmCropSeason rows require `organisation_id`.
- Farm member choices and crop-season crop choices are built only from the active organisation.
- Farm, crop, and season detail/edit routes use tenant-scoped querysets; foreign UUIDs return HTTP 404.
- Farm-to-member, season-to-farm, and season-to-crop ownership is validated at model level.
- Search and crop filters begin with an organisation-scoped farm queryset. Unknown, malformed, or foreign crop filters are ignored and never broaden access beyond that queryset.
- Admins and Managers may view and mutate farm and crop records. Field Officers are redirected from the organisation-wide farm list, farm detail, and crop list, and update farms only for assigned members through the Field Workspace (Stage 7).
- Member profiles prefetch and show only farms reachable from the already tenant-scoped member record.

Any later collection or field-work feature must obtain farm and crop references from active-organisation querysets and must not accept an unscoped foreign key from request data.
## Stage 5 collection controls

- Every `CollectionRecord` requires `organisation_id` and links only to a member, crop, and recorder from that organisation.
- Create/edit forms build member and crop choices exclusively from the active organisation. Foreign posted UUIDs fail form validation.
- List, detail, edit, and photo views begin with `.for_organisation(request.organisation)`; guessed foreign record UUIDs return HTTP 404.
- Collection photos are not exposed by a public media route. Authenticated tenant-scoped views stream them after ownership checks.
- Quantity must be positive, price must be nonnegative, and total value is calculated server-side with decimal rounding. Database constraints reinforce these numeric invariants.
- The original `recorded_by` user is assigned by the server and is not editable through request data.
- Unknown, malformed, or foreign member/crop/date filters never broaden the base organisation-scoped queryset.
- Admins and Managers may view and mutate collection records. Field Officers are redirected from the organisation-wide collection list and detail pages, and record collections only for assigned members through the Field Workspace (Stage 7). Collection photos are served to Field Officers only for their assigned members; other photos return 404.

Future finance, field, dashboard, and export code must resolve collection records from the active organisation and must never trust an organisation, member, crop, or recorder identifier supplied by the client without tenant-scoped validation.
## Stage 6 finance controls

Financial records, member choices, lookups, filters, and member-profile history are organisation-scoped. Cross-tenant UUIDs return 404 or fail form/model validation. The recorder is server-controlled. Admins and Managers view and mutate. Field Officers are redirected from finance pages to the Field Workspace; fieldwork does not require financial records.

## Stage 7 field controls

Field Officer access is the intersection of active organisation membership and members assigned to active structure units for which that exact membership is responsible. All visit, farm, and collection actions, and the read-only field member page (`/field/members/<id>/`), resolve the member from this scoped queryset. Cross-tenant and unassigned members return 404. Admins and Managers receive 403 on Field Officer-only actions.

### Field Officer record scope

`apps/organisations/scope.py` is the single owner of role-based record scope:

- `visible_members(request)`: Admins and Managers see all members of the active organisation, including archived members. Field Officers see only members in active units they are responsible for, excluding archived members. The Field Workspace's `assigned_members` delegates to this helper, so the rule has one owner. Archived members remain in historical reports and exports.
- `operational_staff_required`: guards organisation-wide pages (members, groups, farms, crops, collections, finance, reports). Field Officers are redirected to the Field Workspace.
- Member photos, member document downloads, and collection photos filter by `visible_members`, so direct file URLs for out-of-scope members return 404.

New views that show member-related data must use these helpers rather than reimplementing the rule.

## Stage 8 reporting controls

Dashboard metrics, report tables, filters, and export generators begin with tenant-scoped querysets. Foreign member, group, and crop identifiers are ignored rather than broadening scope. Admin/Manager export authorization is enforced server-side. Cross-tenant export tests cover CSV and XLSX content.

## Stage 9 platform controls

Platform organisation list, detail, and status-management routes require Django superuser status. Ordinary organisation users are redirected to login even when authenticated. Suspending or closing an organisation immediately prevents its staff from selecting or accessing that workspace; business data remains stored and isolated.

## Role-aware navigation and landing behavior

Authentication destinations are enforced server-side, not only by navigation visibility:

- KonnectCore Super Admins land in Platform Organisations.
- Organisation Admins and Managers land on the organisation Dashboard.
- Field Officers land in the Field Workspace.
- Direct Field Officer requests for the broad dashboard redirect to the Field Workspace.
- Safe explicit `next` destinations are preserved by Django's login handling.
- Organisation selection and invitation acceptance use the same role-aware destination rules.

The Field Officer sidebar exposes only the Field Workspace. Admin and Manager share operational dashboard access, while staff administration remains Admin-only.

## Demo-data controls

The `seed_demo_data` management command requires an explicit active organisation and an existing active Admin. It is transactional, idempotent, and covered by a two-tenant regression test proving that the non-target organisation remains unchanged. Demo member history does not expose internal seed metadata.
