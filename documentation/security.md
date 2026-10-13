HPQMS Penetration Test — Reconnaissance Phase
Target: 10.10.48.117 (HPQMS — Hospital Patient Queue Management System, own project / lab environment) Phase: Reconnaissance Status: In progress


1. Objective & Scope
This document tracks the reconnaissance phase of a self-directed penetration test against HPQMS, a FastAPI + PostgreSQL application built as a freelance project. The goal of this phase is to map the attack surface — network services, web content, and API structure — before moving into authentication and logic testing.
In scope: 10.10.48.117, all discovered ports/services, the HPQMS web application and API. Out of scope (for now): exploitation, active auth bypass attempts — those belong to later phases.

2. Methodology
Recon follows a layered chain, where each step's output seeds the next:
IP → Ports → Services → Applications → URLs → Endpoints → Parameters → Authentication boundaries
Concretely, for this engagement:
STEP 1  Target              10.10.48.117
STEP 2  Port discovery      80, 443, 135, 5432, 16992
STEP 3  Service discovery   Caddy, HTTPS, PostgreSQL, Windows services
STEP 4  Web discovery       /, /health, /static/...
STEP 5  Technology discovery FastAPI
STEP 6  API discovery       /openapi.json
STEP 7  API groups          auth, patients, visits, queue, routing,
                             departments, staff, tokens, display, admin
Tool chain and why each tool answers a specific question
Tool
Question it answers
nmap
What network services exist?
curl
What does the HTTP service reveal?
whatweb / httpx
What technologies are being used?
ffuf / gobuster
What web resources exist?
Burp Suite
How does the web application communicate?
3. Step 1 — Host & Port Discovery
Question: Is the host up, and what's listening?
# Quick host-alive check
ping -c 3 10.10.48.117

# Full TCP port sweep (all 65535, faster with rate control)
nmap -p- -T4 --min-rate 1000 -oN nmap-allports.txt 10.10.48.117

# Service/version detection + default scripts on discovered ports
nmap -sV -sC -p 80,443,135,5432,16992 -oN nmap-sv.txt 10.10.48.117
Findings:
Port
Service
Confidence
Notes / Follow-up
80/tcp
HTTP (Caddy)
High
—
443/tcp
HTTPS
High
—
135/tcp
MS-RPC
High
Likely host infra, not app-relevant
5432/tcp
PostgreSQL
High
Version not yet confirmed
16992/tcp
Intel AMT (suspected)
Medium
Service unverified — needs direct probe
4. Step 2 — Service Fingerprinting
Question: What exactly is answering on each port, and what version?
# Banner grab / raw response inspection
curl -i http://10.10.48.117/
curl -ik https://10.10.48.117/
curl -L http://10.10.48.117/static - follows the rouet even if a redirect happens

# TLS cert details (often leaks hostnames, org info, SANs)
openssl s_client -connect 10.10.48.117:443 -servername 10.10.48.117 </dev/null 2>/dev/null | openssl x509 -noout -text

# Web stack fingerprinting
whatweb -v http://10.10.48.117/
httpx -title -tech-detect -status-code -u http://10.10.48.117

# PostgreSQL probe (version/banner, no auth)
nmap -p 5432 --script pgsql-brute,banner 10.10.48.117
psql -h 10.10.48.117 -U nonexistent -d postgres   # error message can leak version
Findings: Front server is Caddy (reverse proxy); the JSON response on / indicates a FastAPI app served by Uvicorn behind it. Stack chain: Caddy → Uvicorn → FastAPI.
This matters for recon because FastAPI ships default documentation routes (/docs, /redoc, /openapi.json) — these are checked by default on any FastAPI target.
5. Step 3 — Web Content & Endpoint Discovery
Question: What paths/resources exist that aren't linked from the UI?
# Directory/file brute-force
ffuf -u http://10.10.48.117/FUZZ -w /usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt -mc 200,301,302,403

gobuster dir -u http://10.10.48.117 -w /usr/share/wordlists/dirb/common.txt -x html,js,json

# Known FastAPI metadata endpoints — always check first on FastAPI targets
curl -s http://10.10.48.117/openapi.json | jq .
curl -s http://10.10.48.117/docs
curl -s http://10.10.48.117/redoc
curl -s http://10.10.48.117/health
Discovered web structure:
/
/health
/static/
  kiosk.html
  kiosk-config.js
  css/
  js/
/docs
/redoc        ← blank UI, flagged for investigation
/openapi.json ← full API specification
Open item: /redoc renders blank. This usually means the OpenAPI spec failed to load client-side (CORS, CSP, or a JS error) rather than the route being absent — needs a browser dev-tools check (Console + Network tab), not just curl.
6. Step 4 — API Surface Mapping
Question: What are the authentication boundaries, and where does unauthenticated access stop?
# Pull and pretty-print the full route list from the spec
curl -s http://10.10.48.117/openapi.json | jq '.paths | keys'

# Check which routes respond without auth vs. which 401/403
for path in /api/auth/me /api/patients /api/visits /api/queue; do
  echo "== $path =="
  curl -s -o /dev/null -w "%{http_code}\n" http://10.10.48.117$path
done
Then move into Burp Suite for anything stateful:
• Burp Proxy — intercept the /static/staff-login.html login flow, capture token issuance (/api/auth/login → /api/auth/refresh)
• Burp Repeater — replay auth requests with modified payloads once the request shape is understood (this is where recon ends and auth-boundary testing begins)
Discovered API groups:
/api/auth/
  login
  refresh
  me
  change-password
  complete-admin-setup
  complete-password-change
  me/station
  me/station/bind
  me/station/unbind

Other groups referenced by the spec:
  patients, visits, queue, routing, departments,
  staff, tokens, display, admin
7. Summary Table
Item
Finding
Confidence
Target
10.10.48.117
High
Web HTTP
Port 80
High
Web server
Caddy
High
Web HTTPS
Port 443
High
Windows/RPC
Port 135
High
Database
PostgreSQL on 5432
High
PostgreSQL version
Not precisely identified
Medium
Port 16992
Open, service unidentified
Medium
Application
Hospital Queue Management System
High
Application stack
Caddy → Uvicorn → FastAPI
High
Gobuster Content Discovery (Home Lab — 192.168.1.76)

Command used:

bash
gobuster dir -u http://192.168.1.76/ -w /usr/share/seclists/Discovery/Web-Content/common.txt

Config: GET requests, 10 threads, wordlist common.txt (4,751 entries), 404 set as the negative status code.

Results:

Path	Status	Notes
/docs	200 (961 bytes)	Confirms the FastAPI docs route already found via /openapi.json — independent corroboration from a second tool
/health	200 (15 bytes)	Health check endpoint, previously confirmed via curl
/static	307 → /static/	Trailing-slash redirect, matches earlier curl behavior

Key takeaways:

Gobuster does candidate discovery from a wordlist, not crawling — the two approaches are complementary, not redundant.
A clean result (no /admin, /login, .env, .git) is evidence of absence under this wordlist and status config — not proof those paths don't exist.
Multiple tools agreeing on a finding (/docs via both OpenAPI inspection and Gobuster) increases confidence without extra manual verification.

Updated attack-surface chain:

Nmap → ports (80, 443, 5432, ...)
  ↓
Web fingerprinting → Caddy, Uvicorn, FastAPI
  ↓
Content discovery (Gobuster) → /docs, /health, /static
  ↓
API discovery (OpenAPI) → auth, patients, visits, queue, routing, departments, staff, tokens, display, admin
8. Open Questions / Leads for Next Phase
These came up during API mapping and are not answered in recon — they're hypotheses to carry into auth/logic testing:
• Is complete-admin-setup reachable before an admin account exists, or does it stay exposed afterward?
• Does me/station/bind trust a client-supplied station ID, or validate it server-side?
• Does /api/auth/refresh rotate the issued token, or simply reissue the same one?
• Why does /redoc render blank — CORS/CSP block, or a JS error in spec loading?
• Confirm PostgreSQL version and whether port 5432 is reachable from outside the app tier (should it be?).
• Identify the service on 16992 definitively (Intel AMT would be a host-level finding, not an app one).


9. Next Phase
Authentication & session testing — starting from the /api/auth/* route group and the open questions above.