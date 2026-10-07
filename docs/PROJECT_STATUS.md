# KonnectCore project status and handover

Read this first in any new chat or when a new developer joins. Keep it current: update it in the same commit as any change that affects hosting, operations or the pending list.

Last updated: 2026-10-07. Live release at that time: `363554e`.

## Current state

- The MVP is **live** at https://konnectcore.tech for demos and a small friendly trial.
- All six blocking issues from the original UAT audit are fixed. Later fixes added Cancel invitation, payment allocations, no-store for signed-in pages, Django admin off on the server, and a Content-Security-Policy.
- Test suite: **217 tests pass**.
- Real member data: **not yet**. Use made-up data until a trial data agreement is signed with each organisation.

## Where things are

| Item | Location |
| --- | --- |
| Code (Windows PC) | `D:\KonnectCore` |
| Private GitHub copy | https://github.com/dropinsight50/konnectcore-app (`origin`) |
| Landing page repo (do **not** push the app here) | https://github.com/dropinsight50/KonnectCore- |
| Branches | `main` and `deploy/production` kept on the same commit. The old `fix/pilot-readiness` is merged and local only. |
| Server | Hostinger VPS, Ubuntu 26.04 LTS, 1 CPU, 4 GB RAM, `root@191.215.44.36` |
| SSH key (PC) | `%USERPROFILE%\.ssh\konnectcore_vps_ed25519` |
| Domain | `konnectcore.tech` (A, AAAA and `www` CNAME at Hostinger DNS) |

## Server layout

- `/opt/konnectcore/app`: unpacked release, `compose.prod.yaml`, root-only `.env`, and `RELEASE` (the deployed commit).
- Services: `caddy` (HTTPS, Let's Encrypt, auto-renew), `web` (Django with Gunicorn), `db` (PostgreSQL 17). Only Caddy has public ports.
- `/opt/konnectcore/releases/konnectcore-<commit>.tar.gz`: release packages, kept for rollback.
- Security: key-only SSH, UFW allows 22/80/443 (IPv4 and IPv6), fail2ban, automatic security updates.
- Secrets (`DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`) exist only in the server `.env`. Never print, copy or commit them.

## Deploying a change

1. Tests pass locally: `docker exec konnectcore-web-1 python manage.py test --noinput`. Run only one test run at a time; parallel runs share the test database and fail.
2. Commit on `deploy/production`, then fast-forward `main`.
3. Back up the server first: `/usr/local/sbin/konnectcore-backup`, and check its `SHA256SUMS`.
4. Build the package with `git archive --format=tar.gz HEAD`, copy it with `scp` to `/opt/konnectcore/releases/`, and compare SHA-256 on both ends.
5. On the server, in `/opt/konnectcore/app`: extract the package, write the commit to `RELEASE`, then `docker compose -f compose.prod.yaml up -d --build web`. The database and Caddy are not restarted.
6. Check the web logs, the login page, the headers, and that `/django-admin/` and `/media/` return 404.
7. Push `main` and `deploy/production` to `origin`.

**Rollback:** extract the previous package from `releases/`, set `RELEASE`, and rebuild `web`.

**PowerShell tip:** remote commands containing `$(...)`, `awk` or `${#v}` get mangled by PowerShell. Use single quotes, or send the script base64-encoded and run it with `base64 -d | bash`.

## Backups

- **Server:** `konnectcore-backup.timer` runs `/usr/local/sbin/konnectcore-backup` at about 02:00 UTC. Each backup goes to `/opt/konnectcore/backups/nightly/<timestamp>/` with `db.dump`, `media.tar.gz`, `RELEASE` and `SHA256SUMS`. Backups are kept 14 days.
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

## Security decisions

- Production settings switch on with `DJANGO_SECURE=true`. The app refuses to start with debug on or a weak secret key.
- HSTS is 1 hour, without preload or subdomains, during the trial. Raise it after the trial.
- Signed-in pages send `Cache-Control: no-store, private`.
- Django admin is off on the server unless `DJANGO_ADMIN_ENABLED=true`. Keep it off: it bypasses the organisation privacy rules.
- Content-Security-Policy (`apps/core/middleware.py`): scripts need `nonce="{{ request.csp_nonce }}"`. Inline handlers such as `onsubmit=` are blocked and a test forbids them. Use `data-confirm="..."` on forms for confirmation prompts. Inline styles are still allowed.

## Working rules for agents

- Back up the server before every deploy or data change.
- Ask the owner before deploying, pushing, installing software, changing server login or firewall settings, or touching real organisations' data.
- Never put secrets or passwords in code, docs or commits.
- Browser: use only the dedicated Agent-Zero Chrome profile. List tabs first and act only on tabs you opened for testing.
- Verify claims with commands; report anything not checked as not checked.

## Pending

1. Confirm the first automatic PC backup copy in `D:\KonnectCore-backups\server\pull.log`.
2. Real-phone checklist with a field officer, including Back after sign-out and the payment form with real members.
3. Collect feedback from the Kennedy COOP trial and sort it into fixes and roadmap items.
4. Trial data agreement (Ghana Data Protection Act 2012, Act 843): on hold at the owner's request.
5. Optional: delete the local `fix/pilot-readiness` branch; enable two-factor sign-in on GitHub; raise HSTS after the trial.