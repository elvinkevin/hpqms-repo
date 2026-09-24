# HPQMS Environments — What Is Running, Where, and How They Connect

> **Purpose:** settle the recurring confusion about "which code is actually
> serving requests". Written after the incident where pages loaded fine but
> hit `http://192.168.1.76:8000` — the cause was **stale code running inside
> the Docker containers**, not a bug in the new files. This document is the
> reference for every environment, its URL, its ports, and how the layers
> connect.

---

## 1. The three environments

You are correct — HPQMS has three distinct environments:

| # | Environment | Where the code runs | How it's started | Who uses it |
|---|---|---|---|---|
| 1 | **Local / bare-metal dev** | Python venv on the host (`uvicorn app.main:app`) run from `backend/` | `uvicorn app.main:app --reload` (or similar) in a terminal | Developer only, quick iteration |
| 2 | **Docker (the pilot stack)** | Containers: `hpqms-backend`, `hpqms-postgres`, `hpqms-caddy`, built from `backend/Dockerfile` | `docker compose up -d --build` | **This is what the hospital devices hit** |
| 3 | **Production** | Not deployed yet — same compose stack, intended to run on the hospital server with hardened secrets | Same as (2) + ops policy from RUNBOOK.md | Future |

**Important truth that caused the recent bug:** environments 1 and 2 run
*separate copies of the code*. Editing files on disk changes environment 1
instantly, but **does nothing to the containers** — the backend image bakes
the code in at build time. That is why the old `:8000`-defaulting JavaScript
kept being served: the container was running the pre-fix frontend.

---

## 2. URLs and ports per environment

### Environment 1 — local dev (bare metal)

| What | URL |
|---|---|
| API + frontend | `http://localhost:8000` |
| Health | `http://localhost:8000/health` |
| Database | `postgresql://postgres:password@localhost:5432/hpqms` (from `DATABASE_URL` default in `config.py`) |

Caddy is **not** involved here. Only useful for development; hospital devices
never use this.

### Environment 2 — Docker pilot stack (currently active)

| Entry point | URL | Notes |
|---|---|---|
| **HTTPS + hostname (primary)** | `https://hpqms.internal` | Caddy, TLS internal CA. Requires hosts-entry + CA trust on the device. |
| **HTTP + IP (fallback)** | `http://192.168.1.76` | Caddy plain-HTTP site block, added for TVs/kiosks that can't do TLS or DNS. **No port number — not `:8000`.** |
| Direct backend (LAN) | `http://192.168.1.76:8000` | ⚠️ **Not published anymore.** Docker no longer maps host port 8000; this URL is exactly what the stale-code bug kept producing. It should never be used. |
| Direct backend (internal) | `http://backend:8000` | Container-network name only — reachable by Caddy, not by browsers. |
| Database | `postgres:5432` on the compose network | Not exposed to the host. |

### Environment 3 — production (planned)

Same shape as environment 2, with: production secrets in `backend/.env`,
`ENVIRONMENT=production`, tightened CORS, and the HTTP/IP fallback path
removed once proper DNS + CA distribution exists.

---

## 3. How the layers connect (environment 2)

```text
                     HOSPITAL LAN devices
                      (kiosk, staff PCs, TV displays)
                          │            │
          HTTPS :443 ─────┘            └───── HTTP :80 (fallback, no TLS)
                          ▼                  ▼
                 ┌─────────────────────────────────┐
                 │        hpqms-caddy              │
                 │  ports 80 + 443 published       │
                 │                                 │
                 │  hpqms.internal  → TLS internal │
                 │  192.168.1.76   → plain HTTP    │
                 └───────────────┬─────────────────┘
                                 │  reverse_proxy (Docker network, HTTP)
                                 ▼
                 ┌─────────────────────────────────┐
                 │        hpqms-backend            │
                 │  expose 8000 (internal only —   │
                 │  NOT published to the host)     │
                 │                                 │
                 │  startup: alembic upgrade head  │
                 │           && python bootstrap_admin.py     │
                 │           && uvicorn :8000      │
                 └───────────────┬─────────────────┘
                                 │  postgres:5432 (Docker network)
                                 ▼
                 ┌─────────────────────────────────┐
                 │        hpqms-postgres           │
                 │  data in named volume           │
                 │  not exposed to host            │
                 └─────────────────────────────────┘
```

Key points:

- **Only Caddy has published host ports** (80, 443). The backend and database
  are reachable only through the proxy — that is the intended security
  boundary.
- Both Caddy site blocks forward to the **same** backend, so the hostname
  path and the IP path serve identical content.
- The frontend `js/config.js` now builds API/WebSocket URLs from
  `window.location.host`, so whatever origin the page was loaded from
  (`https://hpqms.internal` or `http://192.168.1.76`) is the origin it calls.
  If a device still requests `:8000`, it is running **cached old JavaScript**
  → hard-refresh (Ctrl+Shift+R) or clear the browser cache.

---

## 4. Which environment is currently running?

The Docker stack (environment 2) is the active deployment — it is the only
one with Caddy, the published ports, and the pilot data. The local
bare-metal environment exists for development but is not what devices use.

**Confirm on your machine** (Docker must be running / in PATH):

```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected:

| Container | Status | Ports |
|---|---|---|
| `hpqms-caddy` | Up | `0.0.0.0:80->80/tcp`, `0.0.0.0:443->443/tcp` |
| `hpqms-backend` | Up (healthy) | *no host port column entry* (expose only) |
| `hpqms-postgres` | Up (healthy) | *no host port column entry* |

If `hpqms-backend` shows a published port like `0.0.0.0:8000->8000`, the
compose file in use is outdated — direct backend access is supposed to be
blocked.

---

## 5. The golden rule that prevents this class of bug

> **After changing any backend or frontend file, the change does not exist
> until you rebuild:**

```powershell
docker compose up -d --build backend
docker compose logs -f backend      # watch migrations + seed + startup complete
```

(`--build` is the part people forget — plain `restart` reuses the old image
and the old code.)

Quick checklist when a device shows unexpected behaviour:

1. **Was the code changed recently?** If yes, `docker compose up -d --build`.
2. Confirm which origin the page was loaded from (look at the browser address
   bar — is it `:8000`? then the device is on a stale bookmark/cached JS).
3. Hard-refresh the device page to drop cached JavaScript.
4. Check `docker compose logs backend --tail 50` for startup/bootstrap lines.

---

## 6. Related documentation

- `documentation/RUNBOOK.md` — daily ops, backups, device onboarding,
  incidents.
- `Caddyfile` — the two site blocks (HTTPS hostname + HTTP IP fallback).
- `docker-compose.yml` — service topology, ports, startup command chain.
