# KonnectCore project status and handover

Read this first in any new chat or when a new developer joins. Keep it current: update it in the same commit as any change that affects hosting, operations or the pending list.

**This file is in the code repository, so keep it safe to share with anyone who has repo access.** Server addresses and logins, key locations, server paths, backup locations, organisation details, test accounts and business plans live in the owner's private operations handover, which is kept outside git. Ask the owner for it. Never add those details here.

Last updated: 2026-10-10. Live release at that time: `a89ac21`.

## Current state

- The MVP is **live** at https://konnectcore.tech for demos and a small friendly trial.
- All six blocking issues from the original UAT audit are fixed. Later fixes added Cancel invitation, payment allocations, no-store for signed-in pages, Django admin off on the server, and a Content-Security-Policy.
- Trial feedback items 1 to 9 from the first trial cooperative are live (see Recent releases). Item 10, voice data entry, is **on hold** until real feedback from more organisations.
- Test suite: **326 tests pass**.
- Real member data: **not yet**. Use made-up data until a data agreement is signed with each organisation.

## Recent releases

| Release | Date | Contents |
| --- | --- | --- |
| `a89ac21` | 2026-10-10 | Zendo-style UI: dark (default) and light theme with a toggle, self-hosted Plus Jakarta Sans and Sora fonts, teal banner on the dashboard, redesigned member profile, KPI icon tiles, initials avatars on the Members list, shared detail-page styles, teal banners on collection, farm, payment and group pages, payment status badge, form labels without colons (site-wide form renderer), lighter Reports layout. No migrations. |
| `b7191ac` | 2026-10-10 | UI feedback from Dennis: balanced form buttons, disabled placeholders, clickable dashboard cards. Live release before `a89ac21`. |
| `473e0f5` | 2026-10-08 | Super Admin Create organisation: Generate from name button for the slug (blank slug is generated server-side, with -2, -3 on clashes); currency dropdown limited to GHS, USD and NGN, default GHS. |
| `a0071d4` | 2026-10-08 | Trial feedback phases 1 to 3: Add wording, menu order, mobile quick-action bar (role-aware), Add Crop farm picker, Use my location on farm forms, farm and crops on Add member, member sorting (Members list and group page), group filter on collections, New member from a group and Save and add members on Create group, 44px tap targets on phones, hashed static files. |
| `f6c6f50` | before 2026-10-08 | SVG icons, initials avatar, password reset links and mobile UI fixes. Live release before `a0071d4`. |

## Repository and branches

- Private GitHub repository (`origin`).
- `main` and `deploy/production` are kept on the same commit. Work is done on `feature/...` branches and fast-forwarded in.
- `docs/` is excluded from release packages (`.gitattributes`: `/docs/** export-ignore`), so these docs never reach the server.

## Hosting overview

- One VPS running Docker Compose with three services: `caddy` (HTTPS with Let's Encrypt), `web` (Django with Gunicorn) and `db` (PostgreSQL 17). Only Caddy has public ports.
- Releases are deployed as `git archive` packages, and each one is kept on the server for rollback.
- Static files: production uses `ManifestStaticFilesStorage`, so CSS and JS get hashed names and browsers never keep stale copies. `web` runs `collectstatic` before Gunicorn; if it fails, `web` does not start. Caddy serves `/static/`. Local dev and tests keep plain names.
- Security: key-only SSH, firewall limited to SSH and HTTP(S), fail2ban, automatic security updates.
- Secrets exist only in the server's root-only `.env`. Never print, copy or commit them.

## Deploying a change

1. Tests pass locally: `docker exec konnectcore-web-1 python manage.py test --noinput` (PostgreSQL). Run only one test run at a time; parallel runs share the test database and fail. Running pytest directly on the PC needs `DB_ENGINE=sqlite`, otherwise it hangs waiting for Postgres.
2. Commit on a `feature/...` branch, then fast-forward `deploy/production` and `main` to it (`git merge --ff-only`).
3. Back up the server first with the backup script, and check its `SHA256SUMS`.
4. Build the package with `git archive --format=tar.gz -o <file> HEAD` (use `-o`; piping through PowerShell corrupts it), copy it to the server's releases folder, and compare SHA-256 on both ends.
5. On the server: confirm the package has no `.env`, extract it into the app folder, write the commit to `RELEASE`, then `docker compose -f compose.prod.yaml up -d --build web`. The database and Caddy are not restarted.
6. Check the web logs (migrations, `collectstatic`, Gunicorn workers, no errors), the login page, the headers, that the hashed CSS and JS load, and that `/django-admin/` and `/media/` return 404.
7. Push `main` and `deploy/production` to `origin` (plain fast-forward, never force).

**Rollback:** extract the previous package, set `RELEASE`, and rebuild `web`. Releases `a0071d4`, `473e0f5` and `a89ac21` had no migrations, so code rollback alone is enough for them.

**PowerShell tip:** remote commands containing `$(...)`, `awk` or `${#v}` get mangled by PowerShell. Use single quotes, or send the script base64-encoded and run it with `base64 -d | bash`.

## Backups

- The server backs up the database, uploaded files and release version nightly, with checksums, kept 14 days.
- A daily scheduled task on the owner's PC pulls a copy and verifies checksums.
- A restore was tested on 2026-10-06 into a temporary database; row counts matched.
- GitHub holds code only. Member data lives only on the server and in these backups.

## Organisations and accounts

- One Super Admin account, owned by the project owner. By policy the Super Admin manages organisations but cannot view their private records. Agents never handle the Super Admin password.
- Trial organisations and test accounts are listed in the private operations handover. Never touch a real organisation's data without the owner's approval.
- New organisations can use GHS, USD or NGN. To add a currency, add one line to `PLATFORM_CURRENCY_CHOICES` in `apps/organisations/forms.py` and deploy.

## Local development

- Local site: `http://localhost:8000` (container `konnectcore-web-1`, which mounts the repo).
- The local database has a demo cooperative with demo staff. Their local passwords are not recorded in the repo. This never affects the live site.

## Security decisions

- Production settings switch on with `DJANGO_SECURE=true`. The app refuses to start with debug on or a weak secret key.
- HSTS is 1 hour, without preload or subdomains, during the trial. Raise it after the trial.
- Signed-in pages send `Cache-Control: no-store, private`.
- Django admin is off on the server unless `DJANGO_ADMIN_ENABLED=true`. Keep it off: it bypasses the organisation privacy rules.
- Content-Security-Policy (`apps/core/middleware.py`): scripts need `nonce="{{ request.csp_nonce }}"`. Inline handlers such as `onsubmit=` are blocked and a test forbids them. Put page behaviour in `static/js/` files (for example `farm_location.js`, `org_slug.js`). Use `data-confirm="..."` on forms for confirmation prompts. Inline styles are still allowed. Calls to outside services are blocked.

## Working rules for agents

- Back up the server before every deploy or data change.
- Ask the owner before deploying, pushing, installing software, changing server login or firewall settings, or touching real organisations' data.
- Never put secrets, passwords, server addresses, logins or business plans in code, docs or commits.
- Browser: use only the dedicated Agent-Zero Chrome profile. List tabs first and act only on tabs you opened for testing.
- Verify claims with commands; report anything not checked as not checked.
- Keep line endings clean: no doubled carriage returns (`\r\r\n`). Check new or edited files before committing.

## Pending

1. **Next feature: available stock view for cooperatives.** Each cooperative sees, by crop, what it has collected (`CollectionRecord`) and what it expects (`FarmCropSeason` estimated yields and dates). Internal only, no publishing. Design to be approved before code.
2. Agreements and consent before real member data: cooperative terms and data processing agreement, member notice wording, consent records on Add member, data protection registration check. Needed before any organisation enters real member data (on hold at the owner's request).
3. Standardise crops, units and region/district (review models first), then an aggregated Super Admin supply dashboard (no names, small groups hidden).
4. Confirm the first automatic PC backup copy in the pull log.
5. Real-phone checklist with a field officer, including Back after sign-out, the payment form with real members, the quick-action bar, and Use my location on HTTPS.
6. Signed-in check on the live site of releases `a0071d4` and `473e0f5` (only HTTP checks were done after deploy).
7. Collect real feedback from a few more organisations: slowest tasks (members, collections, payments), phone use and field signal, languages officers speak with farmers, anything confusing or missing.
8. Ask the trial cooperative (and the new organisations) whether feedback item 8 means a group filter (built) or entering many members' collections at once (possible group batch entry).
9. Feedback item 10, voice data entry: **on hold** at the owner's request until the feedback in item 7 is in. When revisited, start with a spike (speech-to-text provider, languages, server-side keys and cost limits, consent and data protection, CSP).
10. Optional polish: group page buttons on one line on phones, 44px Cancel links, crop checkbox height, lowercase typed organisation slugs.
11. Optional: delete merged local branches; enable two-factor sign-in on GitHub and review repo access; replace root SSH login with a deploy user; raise HSTS after the trial; long cache headers for `/static/` in Caddy.
