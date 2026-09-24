# HPQMS Operations Runbook

> **Audience:** whoever is on duty at the pilot site. This document assumes no
> familiarity with the codebase — only access to the server machine and this
> repository.
>
> **Golden rules:**
> 1. Users reach the system via `https://hpqms.internal` — **never**
>    `https://localhost` (the TLS certificate is issued for `hpqms.internal`).
> 2. Never restore a backup directly into the live `hpqms` database. The
>    restore script enforces this.
> 3. When in doubt, take a backup first: `.\scripts\backup_db.ps1`.

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

The definitive check is the health endpoint (works from any LAN device):

```
https://hpqms.internal/health        ->  {"status":"ok"}
```

Note: from a *new* device you must complete onboarding (§3) first, otherwise
TLS will fail.

### Read application logs

```powershell
docker compose logs backend --tail 100          # recent app + access logs
docker compose logs backend -f                  # live follow
docker compose logs caddy  --tail 50            # TLS/proxy errors
docker compose logs postgres --tail 50          # DB errors (rare, but fatal)
```

Migration and seed output appear in the backend log at each container start —
the 🏥 / 👤 seed lines confirm a clean start.

### Planned stop / start

```powershell
docker compose down            # stops everything; data survives in volumes
docker compose up -d           # start again
```

The stack also survives server reboots (`restart: unless-stopped` on all
services). After a reboot, give the stack ~1 minute, then check `/health`.

---

## 2. Clean-database deployment (fresh install)

This is the full from-zero procedure. It has been verified end-to-end.

**Prerequisites on the target machine:** Docker Desktop (or Engine) running,
this repository cloned, port 80/443 free.

```powershell
# 1. Configure the deployment secrets.
#    Copy the template and fill in real values (see §5 for the policy).
Copy-Item backend\.env.example backend\.env
notepad backend\.env
#    Minimum to set: SECRET_KEY, KIOSK_INTERNAL_API_KEY, and — if the
#    compose file does not already carry them — DATABASE_URL credentials.

# 2. Build and start the whole stack (first build takes a few minutes).
docker compose up -d --build

# 3. Watch the first startup until it settles.
docker compose logs -f backend
#    You should see, in order:
#      - alembic migration output ("running upgrade ... -> head")
#      - seed lines (🏥 departments, service points, 👤 staff)
#      - "Application startup complete"
#    Ctrl+C to stop following (this does NOT stop the container).

# 4. Verify from a browser (after onboarding, §3):
#      https://hpqms.internal/health   -> {"status":"ok"}
#      https://hpqms.internal/static/kiosk.html  -> kiosk page loads
```

The startup command chain (`alembic upgrade head && python bootstrap_admin.py && uvicorn`)
is idempotent: bootstrap creates the initial departments/admin if needed and
reconciles administrator department assignment without changing credentials.
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

## 3. LAN device onboarding (kiosk / staff PC / display board)

Every new device that will use HPQMS needs three things:

### 3.1 Name resolution

The server is reached as `hpqms.internal`. Two options, in order of
preference:

- **Proper DNS entry** on the hospital's internal DNS server:
  `hpqms.internal -> <server IP>` (e.g. `192.168.1.76`).
- **Per-device hosts file** (no DNS control needed):
  - Windows: edit `C:\Windows\System32\drivers\etc\hosts` (as Administrator),
    add: `<server IP>    hpqms.internal`
  - Android (display/kiosk tablets): needs root, or use a private-DNS app.

### 3.2 Trust the internal certificate authority

Caddy generates a private root CA (`tls internal`). Devices must trust it or
browsers show certificate warnings.

- **Export the root CA from the server:**

```powershell
docker compose exec caddy caddy trust          # installs into THIS machine
# To get a copy for other machines, export from the Caddy data volume:
docker run --rm -v hpqms-project_caddy_data:/data -v ${PWD}\backups:/out alpine \
    cp /data/caddy/pki/authorities/local/root.crt /out/hpqms-root.crt
```

- **Windows staff PCs / kiosk PCs:** double-click `hpqms-root.crt`
  → *Install Certificate* → *Local Machine* → **Trusted Root Certification
  Authorities**.
- **Android kiosk tablets:** *Settings → Security → Install from storage*
  (user CA). Note: some apps ignore user CAs; the HPQMS frontend in a browser
  is fine.

### 3.3 Access and accounts

- Always use `https://hpqms.internal` (bookmark it). Never `https://localhost`
  and never the raw server IP — both fail TLS by design.
- Kiosk devices authenticate with the injected API key — no browser
  configuration needed beyond opening
  `https://hpqms.internal/static/kiosk.html`.
- Staff log in with their `employee_id` and password on
  `https://hpqms.internal/static/staff-login.html`.

### Verification checklist for a newly onboarded device

1. `https://hpqms.internal/health` shows `{"status":"ok"}` with **no**
   certificate warning.
2. The kiosk page loads and a (test) check-in succeeds.
3. The staff login works and the dashboard receives live queue updates
   (WebSocket path — the most integration-sensitive piece).

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

Current secrets and where they live:

| Secret | Committed? | Used for |
|---|---|---|
| `SECRET_KEY` | ❌ (compose + `backend/.env`, both git-ignored) | Signs JWTs; knowing it = forging staff sessions |
| `KIOSK_INTERNAL_API_KEY` | ❌ (same) | Kiosk devices calling `/api/kiosk/*` |
| `POSTGRES_PASSWORD` | ❌ in compose (git-ignored? **verify**) | DB access; currently internal-network only |
| Caddy internal CA root | in volume | TLS trust for LAN devices |

**Policy going forward:**

1. Secrets never enter source control. If one ever does, **rotate it** —
   rotation (below) makes the leaked value worthless, which is why we don't
   rewrite history.
2. Rotate `SECRET_KEY` and `KIOSK_INTERNAL_API_KEY`:
   - Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   - Update `docker-compose.yml` + `backend/.env`, then
     `docker compose up -d backend`.
   - Effect: all existing JWTs die instantly (everyone re-logs in — expected),
     and kiosk devices must refresh their page (key is injected at serve time,
     so no device-side work).
3. Rotate the DB password (more moving parts — plan a maintenance window):
   `ALTER USER hpqms WITH PASSWORD '...'` inside the container, update
   `DATABASE_URL` in compose + `backend/.env`, `docker compose up -d backend`.
4. `backend/.env.example` stays a placeholder forever — it documents shape,
   not values.

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
