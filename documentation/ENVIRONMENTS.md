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
| 2 | **Docker (local/pilot)** | Containers: `hpqms-backend`, `hpqms-postgres`, `hpqms-caddy`, built from `backend/Dockerfile` | `docker compose up -d --build` | Local testing or private LAN |
| 3 | **Production** | Same Compose stack on the VPS, with production secrets and public DNS | Follow `documentation/RUNBOOK.md` | Public users at `https://hpqms.cloud` |

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
| Database | `postgres:5432` on the Compose network |

Caddy is **not** involved here. Only useful for development; hospital devices
never use this.

### Environment 2 — Docker (local/pilot)

The current Caddy configuration is for the production VPS hostname, not a
standalone local Docker test. For quick local development use the bare-metal
environment above. On the VPS, Caddy serves `https://hpqms.cloud`.

| Service | Address | Notes |
|---|---|---|
| Caddy | `https://hpqms.cloud` | Production entry point; public DNS and inbound 80/443 must reach the VPS. |
| Backend | `http://backend:8000` | Compose network only; reachable by Caddy, not directly by browsers. |
| PostgreSQL | `postgres:5432` | Compose network only; never publish this port publicly. |

### Environment 3 — production VPS

Uses the same container topology, with `ENVIRONMENT=production`, production
secrets in the ignored root `.env`, and public DNS resolving `hpqms.cloud` to
the VPS. Caddy obtains and renews the public TLS certificate automatically.

---

## 3. How the layers connect (Docker and production)

```text
                     USERS / HOSPITAL DEVICES
                          │
                     HTTPS :443
                          ▼
                 ┌─────────────────────────────────┐
                 │        hpqms-caddy              │
                 │  ports 80 + 443 published       │
                 │                                 │
                 │  hpqms.cloud → public TLS       │
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
- The frontend `js/config.js` now builds API/WebSocket URLs from
  `window.location.host`, so the origin it calls matches the URL used to load it.
  If a device still requests `:8000`, it is running **cached old JavaScript**
  → hard-refresh (Ctrl+Shift+R) or clear the browser cache.

---

## 4. Which environment is currently running?

The Docker stack runs locally or on the VPS depending on where Compose is
started. The production VPS uses `https://hpqms.cloud`; local development can
continue to use the bare-metal environment.

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
docker compose logs -f backend      # watch migrations + bootstrap + startup complete
```

(`--build` is the part people forget — plain `restart` reuses the old image
and the old code.)

Quick checklist when a device shows unexpected behaviour:

1. **Was the code changed recently?** If yes, `docker compose up -d --build`.
2. Confirm the page is loaded from `https://hpqms.cloud`, not a direct
   backend port or old bookmark.
3. Hard-refresh the device page to drop cached JavaScript.
4. Check `docker compose logs backend --tail 50` for startup/bootstrap lines.

---

## 6. Related documentation

- `documentation/RUNBOOK.md` — daily ops, backups, device onboarding,
  incidents.
- `Caddyfile` — public HTTPS hostname and reverse proxy.
- `docker-compose.yml` — service topology, ports, startup command chain.
