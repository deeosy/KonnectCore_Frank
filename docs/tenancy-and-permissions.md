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

Stage 1 currently enforces that only organisation Admins can list, create, or invite staff. Managers and Field Officers receive HTTP 403 for those operations. Organisation users cannot access platform administration.

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
