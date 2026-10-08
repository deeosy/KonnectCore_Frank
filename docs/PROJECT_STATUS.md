# KonnectCore project status and handover

Read this first in any new chat or when a new developer joins. Keep it current: update it in the same commit as any change that affects hosting, operations or the pending list.

Last updated: 2026-10-08. Live release at that time: `473e0f5`.

## Current state

- The MVP is **live** at https://konnectcore.tech for demos and a small friendly trial.
- All six blocking issues from the original UAT audit are fixed. Later fixes added Cancel invitation, payment allocations, no-store for signed-in pages, Django admin off on the server, and a Content-Security-Policy.
- Kennedy COOP trial feedback items 1 to 9 are live (see Recent releases). Item 10, voice data entry, is not started.
- Test suite: **319 tests pass**.
- Real member data: **not yet**. Use made-up data until a trial data agreement is signed with each organisation.

## Recent releases

| Release | Date | Contents |
| --- | --- | --- |
| `473e0f5` | 2026-10-08 | Super Admin Create organisation: Generate from name button for the slug (blank slug is generated server-side, with -2, -3 on clashes); currency dropdown limited to GHS, USD and NGN, default GHS. |
| `a0071d4` | 2026-10-08 | Kennedy feedback phases 1 to 3: Add wording, menu order, mobile quick-action bar (role-aware), Add Crop farm picker, Use my location on farm forms, farm and crops on Add member, member sorting (Members list and group page), group filter on collections, New member from a group and Save and add members on Create group, 44px tap targets on phones, hashed static files. |
| `f6c6f50` | before 2026-10-08 | SVG icons, initials avatar, password reset links and mobile UI fixes. This was the live release before `a0071d4`; the previous version of this file named `363554e`. |

## Where things are

| Item | Location |
| --- | --- |
| Code (Windows PC) | `D:\KonnectCore` |
| Private GitHub copy | https://github.com/dropinsight50/konnectcore-app (`origin`) |
| Landing page repo (do **not** push the app here) | https://github.com/dropinsight50/KonnectCore- |
| Branches | `main` and `deploy/production` kept on the same commit. Work is done on `feature/...` branches and fast-forwarded in. `feature/kennedy-feedback` and `feature/superadmin-org-form` are fully merged (also on GitHub). The old `fix/pilot-readiness` is merged and local only. |
| Server | Hostinger VPS, Ubuntu 26.04 LTS, 1 CPU, 4 GB RAM, `root@191.215.44.36` |
| SSH key (PC) | `%USERPROFILE%\.ssh\konnectcore_vps_ed25519` |
| Domain | `konnectcore.tech` (A, AAAA and `www` CNAME at Hostinger DNS) |

## Server layout

- `/opt/konnectcore/app`: unpacked release, `compose.prod.yaml`, root-only `.env`, and `RELEASE` (the deployed commit).
- Services: `caddy` (HTTPS, Let's Encrypt, auto-renew), `web` (Django with Gunicorn), `db` (PostgreSQL 17). Only Caddy has public ports.
- `/opt/konnectcore/releases/konnectcore-<commit>.tar.gz`: release packages, kept for rollback.
- Static files: production uses `ManifestStaticFilesStorage`, so CSS and JS get hashed names (for example `app.7661bcd23c40.css`) and browsers never keep stale copies. `web` runs `collectstatic` before Gunicorn; if it fails, `web` does not start. Caddy serves `/static/` from the shared `static_data` volume. Local dev and tests keep plain names.
- Security: key-only SSH, UFW allows 22/80/443 (IPv4 and IPv6), fail2ban, automatic security updates.
- Secrets (`DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`) exist only in the server `.env`. Never print, copy or commit them.

## Deploying a change

1. Tests pass locally: `docker exec konnectcore-web-1 python manage.py test --noinput` (PostgreSQL). Run only one test run at a time; parallel runs share the test database and fail. Running pytest directly on the PC needs `DB_ENGINE=sqlite`, otherwise it hangs waiting for Postgres.
2. Commit on a `feature/...` branch, then fast-forward `deploy/production` and `main` to it (`git merge --ff-only`).
3. Back up the server first: `/usr/local/sbin/konnectcore-backup`, and check its `SHA256SUMS`.
4. Build the package with `git archive --format=tar.gz -o <file> HEAD` (use `-o`; piping through PowerShell corrupts it), copy it with `scp` to `/opt/konnectcore/releases/`, and compare SHA-256 on both ends.
5. On the server, in `/opt/konnectcore/app`: confirm the package has no `.env`, extract it, write the commit to `RELEASE`, then `docker compose -f compose.prod.yaml up -d --build web`. The database and Caddy are not restarted.
6. Check the web logs (migrations, `collectstatic`, Gunicorn workers, no errors), the login page, the headers, that the hashed CSS and JS load, and that `/django-admin/` and `/media/` return 404.
7. Push `main` and `deploy/production` to `origin` (plain fast-forward, never force).

**Rollback:** extract the previous package from `releases/`, set `RELEASE`, and rebuild `web`. Releases `a0071d4` and `473e0f5` had no migrations, so code rollback alone is enough for them.

**PowerShell tip:** remote commands containing `$(...)`, `awk` or `${#v}` get mangled by PowerShell. Use single quotes, or send the script base64-encoded and run it with `base64 -d | bash`.

## Backups

- **Server:** `konnectcore-backup.timer` runs `/usr/local/sbin/konnectcore-backup` at about 02:00 UTC. Each backup goes to `/opt/konnectcore/backups/nightly/<timestamp>/` with `db.dump`, `media.tar.gz`, `RELEASE` and `SHA256SUMS`. Backups are kept 14 days. Latest pre-deploy backup: `20261008-104346` (release `a0071d4`).
- **PC copy:** the Windows scheduled task *KonnectCore server backup pull* runs daily at 09:00 (while signed in). It uses `D:\KonnectCore-backups\pull-server-backup.ps1`, writes to `D:\KonnectCore-backups\server\` and logs to `pull.log`. It keeps 14 copies and verifies checksums.
- **Restore** was tested on 2026-10-06 into a temporary database; row counts matched.
- GitHub holds code only. Member data lives only in the server and these backups.

## Organisations on the live site

| Organisation | Purpose | Rule |
| --- | --- | --- |
| KonnectCore Demo | Prospect demos, with fictional sample data. Its 3 sample staff accounts cannot sign in. | Keep tidy |
| Kennedy COOP (`kn-001`) | A friend's trial | **Do not touch.** Owner-approved access only. |
| QA Live Check (`qa-live-check`) | Live testing | Test accounts `qa_live_admin@example.test` (Admin) and `qa_live_field@example.test` (Field Officer). Passwords are not recorded here; use for testing only. |

There is one Super Admin account, owned by the project owner. By policy the Super Admin manages organisations but cannot view their private records. Agents never handle the Super Admin password.

New organisations can use GHS, USD or NGN. To add a currency, add one line to `PLATFORM_CURRENCY_CHOICES` in `apps/organisations/forms.py` and deploy.

## Local development

- Local site: `http://localhost:8000` (container `konnectcore-web-1`, mounts `D:\KonnectCore`).
- The local database has the demo cooperative (`demo-cooperative`) with demo staff such as `manager@demo.konnectcore.local` and `field.north@demo.konnectcore.local`. Their local passwords were reset for testing and are not recorded here. This never affects the live site.

## Security decisions

- Production settings switch on with `DJANGO_SECURE=true`. The app refuses to start with debug on or a weak secret key.
- HSTS is 1 hour, without preload or subdomains, during the trial. Raise it after the trial.
- Signed-in pages send `Cache-Control: no-store, private`.
- Django admin is off on the server unless `DJANGO_ADMIN_ENABLED=true`. Keep it off: it bypasses the organisation privacy rules.
- Content-Security-Policy (`apps/core/middleware.py`): scripts need `nonce="{{ request.csp_nonce }}"`. Inline handlers such as `onsubmit=` are blocked and a test forbids them. Put page behaviour in `static/js/` files (for example `farm_location.js`, `org_slug.js`). Use `data-confirm="..."` on forms for confirmation prompts. Inline styles are still allowed. Calls to outside services are blocked.

## Working rules for agents

- Back up the server before every deploy or data change.
- Ask the owner before deploying, pushing, installing software, changing server login or firewall settings, or touching real organisations' data.
- Never put secrets or passwords in code, docs or commits.
- Browser: use only the dedicated Agent-Zero Chrome profile. List tabs first and act only on tabs you opened for testing.
- Verify claims with commands; report anything not checked as not checked.
- Keep line endings clean: no doubled carriage returns (`\r\r\n`). Check new or edited files before committing.

## Pending

1. Confirm the first automatic PC backup copy in `D:\KonnectCore-backups\server\pull.log`.
2. Real-phone checklist with a field officer, including Back after sign-out, the payment form with real members, the quick-action bar, and Use my location on HTTPS.
3. Signed-in check on the live site of releases `a0071d4` and `473e0f5` (only HTTP checks were done after deploy).
4. Kennedy feedback item 10, voice data entry: not started. Start with a spike (speech-to-text provider, server-side keys and cost limits, consent and data protection, CSP). Confirm Deepgram Nova-2 vs Nova-3 with Kennedy.
5. Ask Kennedy whether item 8 means a group filter (built) or entering many members' collections at once (possible group batch entry).
6. Optional polish: group page buttons on one line on phones, 44px Cancel links, crop checkbox height, lowercase typed organisation slugs.
7. Trial data agreement (Ghana Data Protection Act 2012, Act 843): on hold at the owner's request.
8. Optional: delete merged local branches (`fix/pilot-readiness`, `feature/kennedy-feedback`, `feature/superadmin-org-form`); enable two-factor sign-in on GitHub; raise HSTS after the trial; long cache headers for `/static/` in Caddy.
