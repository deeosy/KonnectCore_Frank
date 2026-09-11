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
- **Field Officer**: restricted field workflows and assigned scope in later stages.
- **KonnectCore Super Admin**: platform owner identity using Django superuser status; not an organisation role.

Stage 1 enforces that only organisation Admins can list, create, or invite staff. Managers and Field Officers receive HTTP 403 for those operations. Organisation users cannot access platform administration.

Stage 2 allows all active staff roles to view tenant-scoped member lists and profiles. Admins and Managers can register/edit members, attach documents, and import records. Field Officers remain read-only until assigned-member field workflows are implemented in Stage 7. Member detail, edit, file, search, and import operations are all derived from `request.organisation`; cross-tenant UUID guessing returns 404.

Stage 3 applies the same policy to organisation structure. All active roles can view units and assignments; Admins and Managers can create/edit units and add/remove members. Parent units, leaders, responsible Field Officers, and assigned members must all belong to the active organisation. Responsible officers must be active Field Officer memberships. Hierarchy cycles and duplicate sibling/root names are rejected.

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
- Admins and Managers may mutate farm and crop records. Field Officers are read-only in Stage 4.
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
- Admins and Managers may mutate collection records. Field Officers are read-only in Stage 5; assigned-member collection entry belongs to Stage 7.

Future finance, field, dashboard, and export code must resolve collection records from the active organisation and must never trust an organisation, member, crop, or recorder identifier supplied by the client without tenant-scoped validation.
## Stage 6 finance controls

Financial records, member choices, lookups, filters, and member-profile history are organisation-scoped. Cross-tenant UUIDs return 404 or fail form/model validation. The recorder is server-controlled. Admins and Managers mutate; Field Officers are read-only.

## Stage 7 field controls

Field Officer access is the intersection of active organisation membership and members assigned to active structure units for which that exact membership is responsible. All visit, farm, and collection actions resolve the member from this scoped queryset. Cross-tenant and unassigned members return 404.
