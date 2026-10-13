# HPQMS Operations Runbook

> **Audience:** whoever operates the HPQMS VPS.
>
> **Golden rules:**
> 1. Users reach the system via `https://hpqms.cloud` — never the backend or
>    database ports directly.
> 2. Never restore a backup directly into the live `hpqms` database. The
>    restore script enforces this.
> 3. When in doubt, take a backup first and verify that it can be restored.

---

## 1. Daily operations

### Check the system is alive

```powershell
# From the server, quick status of all containers:
docker ps
```

Expected state:

| Container        | Status                          |
|------------------|---------------------------------|
| `hpqms-caddy`    | Up, ports 80 + 443 published    |
| `hpqms-backend`  | Up **(healthy)**, no host ports |
| `hpqms-postgres` | Up **(healthy)**, no host ports |

The definitive check is the public health endpoint:

```
https://hpqms.cloud/health        ->  {"status":"ok"}
```

The certificate should be trusted by browsers automatically. If the site
doesn't load, check DNS, the VPS firewall, and Caddy logs.

### Read application logs

```powershell
docker compose logs backend --tail 100          # recent app + access logs
docker compose logs backend -f                  # live follow
docker compose logs caddy  --tail 50            # TLS/proxy errors
docker compose logs postgres --tail 50          # DB errors (rare, but fatal)
```

Migration and administrator bootstrap output appear in backend logs at
container startup.

### Planned stop / start

```powershell
docker compose down            # stops everything; data survives in volumes
docker compose up -d           # start again
```

The stack also survives server reboots (`restart: unless-stopped` on all
services). After a reboot, give the stack ~1 minute, then check `/health`.

---

## 2. Production VPS deployment (fresh install)

This procedure assumes the provider has given you a public IPv4 address and
you control DNS for `hpqms.cloud`.

**Prerequisites:** a Linux VPS with Docker Engine and the Compose plugin
installed; the repository cloned on the VPS; ports 80 and 443 allowed through
both the provider firewall and the VPS firewall; and DNS for `hpqms.cloud`
pointing to the VPS. In HostAfrica DNS, create an `A` record for `@` pointing
to `102.68.86.149`. Do not add an `AAAA` record unless the VPS has working
IPv6. This Caddy configuration serves `hpqms.cloud` (not `www.hpqms.cloud`).

Allow SSH and web traffic in the VPS firewall, keeping your SSH access allowed
before changing firewall rules. For UFW, for example:

```sh
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw status
```

Apply the corresponding inbound rules in the provider firewall as well. Do not
open ports 5432 (PostgreSQL) or 8000 (FastAPI) to the internet.

On the VPS, from the repository root:

```sh
# 1. Create the private Compose environment file.
cp .env.example .env
chmod 600 .env
nano .env
#    Set POSTGRES_PASSWORD, SECRET_KEY (at least 32 characters),
#    KIOSK_INTERNAL_API_KEY, INITIAL_ADMIN_EMPLOYEE_ID, and
#    INITIAL_ADMIN_PASSWORD (at least 12 characters).
#    Generate a separate URL-safe value for each secret, e.g.:
#      python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
#    Keep ENVIRONMENT=production. Use a URL-safe password for PostgreSQL.

# 2. Check the Compose configuration, then build and start the stack.
docker compose config --quiet
docker compose up -d --build

# 3. Watch startup until migrations, admin bootstrap, and the app complete.
docker compose logs -f backend
#    You should see, in order:
#      - alembic migration output ("running upgrade ... -> head")
#      - administrator bootstrap confirmation
#      - "Application startup complete"
#    Press Ctrl+C to stop following logs (this does NOT stop the container).

# 4. Verify public HTTPS and application health.
curl -fsS https://hpqms.cloud/health
```

The Caddyfile uses `hpqms.cloud` as its site name. Caddy automatically obtains
and renews a publicly trusted TLS certificate; no internal CA installation or
separate certificate file is needed. Certificate issuance requires public DNS
to resolve to this VPS and inbound ports 80 and 443 to reach it. HTTP requests
are redirected to HTTPS automatically.

The startup command chain (`alembic upgrade head && python bootstrap_admin.py && uvicorn`)
is idempotent: bootstrap creates the initial departments/admin when required
and reconciles administrator department assignment without changing
credentials.
Re-running `docker compose up -d` on an existing volume **does not wipe data**.

### Wiping the database intentionally (demo/reset)

⚠️ **Destructive.** Never do this on a server holding real patient data
(back up first with §4).

```powershell
docker compose down                       # keep the volume? then skip next line
docker volume rm hpqms-project_hpqms_postgres_data
docker compose up -d --build              # fresh DB + migrations + admin bootstrap
```

### Deploying a code update

```powershell
git pull
docker compose up -d --build backend      # rebuilds image, reruns migrations
docker compose logs -f backend            # confirm migrations + startup
```

No database changes are required for normal updates — migrations apply
automatically at startup. If a migration is destructive it will be called out
in the release notes; back up first (§4).

---

## 3. User access (staff / kiosk / display board)

Use the public HTTPS hostname from each device:

- Health: `https://hpqms.cloud/health`
- Kiosk: `https://hpqms.cloud/static/kiosk.html`
- Staff login: `https://hpqms.cloud/static/staff-login.html`

Browsers should show a valid HTTPS connection without installing a private
certificate authority. Verify staff login and live queue updates (WebSockets)
after deployment.

---

## 4. Backups & restore

### Take a backup

```powershell
.\scripts\backup_db.ps1                 # keeps the last 7 dumps
.\scripts\backup_db.ps1 -KeepCount 30   # different retention for this run
.\scripts\backup_db.ps1 -NoPrune        # archival run, delete nothing
```

Each run: dumps live `hpqms` (custom format) → `backups/hpqms_backup_YYYYMMDD_HHMMSS.dump`
→ **integrity-verifies the archive** (`pg_restore --list` on the actual bytes;
a failed verification deletes the bad file immediately rather than leaving a
dump that would fail mid-restore) → prunes oldest dumps beyond the retention
count.

### Scheduled daily backup (recommended)

Use Windows Task Scheduler on the server — no extra containers:

- **Trigger:** daily, e.g. 02:00.
- **Action:** start a program → program: `powershell.exe`, arguments:
  `-ExecutionPolicy Bypass -File "C:\path\to\hqms-project\scripts\backup_db.ps1"`
- **Start in:** the project root directory (docker compose needs it, or add
  a `Set-Location` line at the top of the script).

Verify the schedule produced files in `backups/` the next morning.

### Restore (to a scratch database — never the live one)

```powershell
.\scripts\restore_db.ps1
```

The script: lists available dumps → asks which to use → asks for a **target
database name** → **refuses the name `hpqms`** → requires typing `RESTORE` →
drops/recreates the target → `pg_restore --clean --if-exists`.

### Restore drill (do this after setup, and after any major version change)

This proves the backups are actually recoverable — the only property that
matters. Verified procedure:

```powershell
# 1. Fresh backup
.\scripts\backup_db.ps1

# 2. Restore the newest dump into a scratch DB (use restore_db.ps1, or:)
#    (manual equivalent shown for scripting)
docker compose exec postgres psql -U hpqms -d postgres \
    -c "DROP DATABASE IF EXISTS hpqms_drill;" -c "CREATE DATABASE hpqms_drill;"
docker compose cp backups\<newest>.dump postgres:/tmp/drill.dump
docker compose exec postgres pg_restore -U hpqms -d hpqms_drill --clean --if-exists /tmp/drill.dump

# 3. Compare row counts live vs restored (must all match):
#    departments, staff, patients, visits, queue_entries, vitals, service_points, alembic_version
docker compose exec postgres psql -U hpqms -d hpqms        -t -A -c "SELECT COUNT(*) FROM staff;"
docker compose exec postgres psql -U hpqms -d hpqms_drill  -t -A -c "SELECT COUNT(*) FROM staff;"

# 4. Clean up the drill
docker compose exec postgres psql -U hpqms -d postgres -c "DROP DATABASE hpqms_drill;"
```

Result of the first drill (all counts matched): departments 4, staff 12,
service_points 10, alembic_version 1.

**Off-site copy:** `backups/` lives on the same machine as the database. A
disk failure takes both. At minimum, copy the newest dump to a USB/NAS/other
machine weekly; the retention prune never touches files you copied away.

---

## 5. Secrets & rotation policy

Deployment secrets are supplied through the ignored root `.env` file (or an
equivalent protected environment on the deployment host). Never put actual
secret values in the Compose file, `backend/.env.example`, or source control.
Earlier versions had credential values in tracked files, so generate new
values for the VPS; editing the current files does not remove values from Git
history.

| Secret | Configured in | Used for |
|---|---|---|
| `SECRET_KEY` | root `.env` | Signs JWTs; knowing it = forging staff sessions |
| `KIOSK_INTERNAL_API_KEY` | root `.env` | Kiosk devices calling `/api/kiosk/*` |
| `POSTGRES_PASSWORD` | root `.env` | Database access; backend connection is private to Compose |
| Initial admin credentials | root `.env` | Creates the first administrator on a fresh database |
| Caddy certificate state | `caddy_data` Docker volume | Public TLS certificate renewal |

**Policy going forward:**

1. Secrets never enter source control. If one ever does, **rotate it** —
   rotation (below) makes the leaked value worthless, which is why we don't
   rewrite history.
2. Rotate `SECRET_KEY` and `KIOSK_INTERNAL_API_KEY`:
   - Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   - Update the values in the root `.env`, then
     `docker compose up -d --force-recreate backend`.
   - Effect: all existing JWTs die instantly (everyone re-logs in — expected),
     and kiosk devices must refresh their page (key is injected at serve time,
     so no device-side work).
3. Rotate the DB password (more moving parts — plan a maintenance window):
   use `docker compose exec postgres psql -U hpqms -d hpqms` and run
   `\password hpqms` to set the new password without putting it in shell
   history. Update `POSTGRES_PASSWORD` in the root `.env` using a URL-safe
   value, then recreate the backend with
   `docker compose up -d --force-recreate backend`.
4. The `.env.example` files are blank templates; store real values only in
   ignored `.env` files or a protected deployment environment.

---

## 6. Incident procedures

### Backend unhealthy / system unreachable

```powershell
docker compose ps                     # who is unhealthy?
docker compose logs backend --tail 200
docker compose restart backend
```

If the backend crash-loops, the log will show why (migration failure,
DB unreachable, bad config). Do not disable the healthcheck to "fix" it.

### Database down / corrupt

```powershell
docker compose logs postgres --tail 100
docker compose restart postgres       # safe: data is in a volume
```

If the data volume itself is lost: rebuild with §2, then restore the newest
verified dump into `hpqms` via `restore_db.ps1` **with the guard adjusted by
hand** — for a true disaster restore the script's `hpqms` protection is
bypassed deliberately, in a maintenance window, after a backup of whatever
remains.

### Disk full

Fastest space recovery, in order of safety:
`backups/` dumps (each ~80 KB now, but grows with data), docker image cache
(`docker image prune`), container logs (`docker compose logs --tail 0`
rotates nothing — configure log rotation in Docker Desktop settings).

### Display boards frozen / WebSocket dead

The boards poll `/api/display/snapshot` on a timer as fallback, so they go
stale rather than blank. Usual causes: board slept (wake it), or backend
restarted (reload the board page — reconnect is automatic). If several boards
die at once, suspect the proxy/backend, not the boards.

### When HPQMS is fully down during clinic hours

Fallback is the paper register (the process the pilot replaces). Rebuild from
the paper queue when the system returns: register walk-in patients, start
visits, and let the token sequence continue — tokens restart per department
per day, so a downtime day does not corrupt numbering.

---

## 7. Known limitations (honest list)

| Limitation | Consequence | When it will change |
|---|---|---|
| Single uvicorn worker | ~capacity ceiling; restart drops in-flight requests | After Redis pub/sub lands (Phase 3) |
| In-memory WebSocket fan-out | All boards/staff must hit the same process | Redis pub/sub |
| In-memory rate limiter | Limits are per-process; restart resets counters | Redis backend (same change) |
| No Lab / Pharmacy modules | OPD-only pilot scope | Phase B/C |
| Backups on the same machine | Server disk failure = data loss window | Off-site copy policy in §4 |
| No monitoring/alerting | Failures are found by users, not by us | Phase 3 (Prometheus/Grafana) |
| `SECRET_KEY`/DB password in plain files | Adequate for pilot; hospital infra may require vaulting | Site security review |

---

*Verified against the live stack: 2026-09-21. Update the verification date in
§4's drill log whenever a drill is re-run.*
