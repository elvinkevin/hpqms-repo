                 HOSPITAL LAN
                      │
                      │ HTTPS :443
                      ▼
             ┌─────────────────┐
             │      CADDY      │
             │                 │
             │ • TLS           │
             │ • Internal CA   │
             │ • Reverse Proxy │
             └────────┬────────┘
                      │
                      │ HTTP :8000
                      ▼
             ┌─────────────────┐
             │    FASTAPI      │
             │ hpqms-backend   │
             │                 │
             │ /api            │
             │ /ws/display     │
             │ /static         │
             │ /health         │
             └────────┬────────┘
                      │
                      │ PostgreSQL
                      ▼
             ┌─────────────────┐
             │  POSTGRESQL 16  │
             │ hpqms-postgres  │
             │                 │
             │ Docker network  │
             └─────────────────┘


             Employee ID: EMP-RECEP01
Temporary password: AiijB!o4TdtVmARU2P