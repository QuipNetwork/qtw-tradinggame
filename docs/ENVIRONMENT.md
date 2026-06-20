# Environment Configuration

This project has three runtime surfaces:

- Netlify hosts the React frontend in `mvp/`.
- A long-lived backend process hosts FastAPI inside a Docker container on a
  DigitalOcean droplet.
- Supabase hosts Postgres only. The browser should never connect to Postgres.

## Local Defaults

With no production env vars set:

- Frontend uses mock API data unless `VITE_API_BASE` is set.
- Backend uses in-memory stores unless `DATABASE_URL` is set.
- Backend uses `assets-api` by default for market data.
- Backend points at `https://asset-tracker.quip.network` by default.
- Tests force in-memory stores and synthetic market data.
- Email sending is not wired yet; signup currently stores email/consent only.
- The backend has a Dockerfile and GitLab CI deployment scaffold. The remaining
  external step is provisioning the droplet and setting CI/CD variables.

## Frontend Env - Netlify

Set these in Netlify project environment variables.

| Variable | Required | Example | Notes |
|---|---:|---|---|
| `VITE_API_BASE` | yes for production | `https://api.qtw.quip.network` | Browser HTTP requests to FastAPI. |
| `VITE_WS_BASE` | no | `https://api.qtw.quip.network` | Only set if websocket traffic is hosted somewhere different from HTTP API traffic. |

Do not put database passwords, SMTP tokens, D-Wave tokens, or Supabase service
keys in Netlify frontend env.


## Backend Env - FastAPI Container

Set these on the backend host/container, not in browser-visible env.
On the droplet, store them in:

```text
/opt/qtw/backend.env
```

| Variable | Required | Example | Notes |
|---|---:|---|---|
| `DATABASE_URL` | yes | `postgresql://postgres.<project-ref>:<password>@aws-1-us-west-2.pooler.supabase.com:5432/postgres` | Enables Supabase/Postgres persistence. Use the Supabase pooler when direct IPv6 DB host is not reachable. |
| `APP_ENV` | yes | `production`, `booth`, `local-smoke-azain` | Stored with DB rows so local/test rows can be cleaned up safely. |
| `QR_BASE_URL` | yes | `https://qtw.quip.network` | Base for generated phone profile QR URLs. |
| `ASSETS_API_BASE_URL` | yes | `https://asset-tracker.quip.network` | Market-data service consumed by backend. |
| `DWAVE_API_TOKEN` | yes for QPU booth mode | `<Leap token>` | Enables D-Wave/QPU participation. Without it, the D-Wave provider is omitted. |
| `GUROBI_IN_RACE` | yes | `0` | Keep `0` in production; Gurobi is local/dev only unless deployment has a valid license. |
| `VALUATION_SNAPSHOT_INTERVAL_S` | no | `60` | Durable analytics snapshot cadence. Use `0` to disable snapshots. |
| `QPU_BUDGET_MAX_ATTEMPTS` | no | `3` | Per-agent QPU-admitted solves allowed per rolling window. |
| `QPU_BUDGET_WINDOW_S` | no | `600` | Rolling QPU budget window in seconds. |

`MARKET_DATA_SOURCE` defaults to `assets-api`, so production usually does not
need to set it. Set `MARKET_DATA_SOURCE=synthetic` only for offline demos or
debugging without real market data.

D-Wave tuning knobs such as `DWAVE_NUM_READS`, `DWAVE_ANNEAL_TIME_US`, and
`DWAVE_CHAIN_STRENGTH_PREFACTOR` have code defaults. Do not put them in the
normal production env unless you are deliberately running a hardware tuning
pass.

The QPU budget defaults to 3 QPU-admitted solves per agent per 10 minutes.
First solve, manual retune, and scheduled rebalance share that budget. Manual
over-budget requests return 429 with `Retry-After`; scheduled over-budget
rebalances defer to the next budget opening.

Assets-api retry/logging knobs such as `ASSETS_API_RETRIES`,
`ASSETS_API_RETRY_BACKOFF_S`, and `MTM_ERROR_LOG_INTERVAL_S` also have code
defaults. Set them only if production logs show a specific need.

`MTM_TICK_S` is not part of the normal production env yet. The backend still
defaults to a 3s MTM loop, but the next planned change is to align this with the
assets-api spot refresh cadence after that service owns faster spot freshness.

## Supabase/Postgres

Store `DATABASE_URL` only on the backend host/container. The browser and
Netlify frontend must never receive the database password.

For local testing, the direct Supabase database URL may fail if your network
does not support the direct IPv6 database host:

```text
postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
```

Use Supabase's session pooler instead:

```text
postgresql://postgres.<project-ref>:<password>@aws-1-us-west-2.pooler.supabase.com:5432/postgres
```

For this project, the local smoke-test pooler shape is:

```text
postgresql://postgres.aisaxqzormmkumfgvpst:<password>@aws-1-us-west-2.pooler.supabase.com:5432/postgres
```

If using a single Supabase project for local and production:

- Run local DB tests with `APP_ENV=local`.
- Run booth/prod with `APP_ENV=production` or `APP_ENV=booth`.
- Clean up local/test rows by filtering on `environment`.
- Back up/export before booth day.

Local backend with `DATABASE_URL` set writes to Supabase. Local backend with
`DATABASE_URL` unset uses in-memory stores and does not write to Supabase.

Cleanup for local smoke-test rows:

```sql
begin;

delete from valuation_snapshots where environment = 'local';
delete from solve_snapshots where environment = 'local';
delete from jobs where environment = 'local';
delete from qpu_budget_events where environment = 'local';
delete from agent_holdings where environment = 'local';
delete from agents where environment = 'local';

commit;
```

Restart the local backend after cleanup because the running process may still
hold the old working set in memory.

## Proton SMTP

Status: not implemented yet.

The current backend stores email/consent fields on agent creation, including in
Supabase when `DATABASE_URL` is set. There is no SMTP sender module and no route
currently sends email.

When implemented, email sending should be backend-only. Supabase stores
email/consent; FastAPI will send through Proton SMTP using backend-only secrets.

Recommended backend env:

| Variable | Required | Example |
|---|---:|---|
| `SMTP_HOST` | yes when email enabled | `smtp.protonmail.ch` |
| `SMTP_PORT` | yes when email enabled | `587` |
| `SMTP_USERNAME` | yes when email enabled | `events@quip.network` |
| `SMTP_PASSWORD` | yes when email enabled | Proton SMTP token |
| `SMTP_FROM` | yes when email enabled | `Quip Network <events@quip.network>` |

Use a Proton SMTP token generated for a custom-domain address. Do not use the
normal Proton account password. Signup should store the user first; an email
send failure should be logged but should not fail signup.

Code changes needed:

- Add SMTP env parsing in `backend/src/backend/config.py`.
- Add an email sender module, likely `backend/src/backend/notifications/email.py`,
  using `smtplib` or a small dependency such as `aiosmtplib`.
- Call the sender after successful `POST /agents` persistence, only when the
  relevant consent/update field says email is allowed.
- Log and continue if SMTP fails; never fail signup because a recap/confirmation
  email failed.
- Add tests with a fake sender so tests never contact Proton.

## Backend Containerization And DigitalOcean

Status: backend image build and GitLab CI deployment scaffold are in place.
The manual deploy job becomes usable after the DigitalOcean droplet exists and
GitLab CI/CD variables are set.

Local/server execution without Docker is still direct Python:

```bash
cd backend
.venv/bin/python -m uvicorn backend.api.app:app --workers 1 --port 8001
```

Chosen production path: **DigitalOcean droplet + Docker**.

Build from the repo root:

```bash
docker build -f backend/Dockerfile -t qtw-backend:local .
```

Run an offline smoke test:

```bash
docker run --rm -p 8001:8000 \
  -e APP_ENV=local-container \
  -e MARKET_DATA_SOURCE=synthetic \
  -e GUROBI_IN_RACE=0 \
  qtw-backend:local
```

Run with a local env file:

```bash
cp backend/.env.example backend/.env.local
docker run --rm --env-file backend/.env.local -p 8001:8000 qtw-backend:local
```

The container command binds publicly inside the container:

```bash
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --workers 1
```

The container exposes `/healthz` for Docker/reverse-proxy checks.

The one-worker constraint is intentional for the first deployment. The websocket
event bus, MTM scheduler, and scheduled rebalance loop are in-process. More than
one worker/container would need an external event bus plus scheduler locking.

### GitLab CI Deploy Automation

`.gitlab-ci.yml` defines:

- `backend:test` — installs the backend package and runs pytest.
- `backend:image` — builds `backend/Dockerfile` with Kaniko and pushes to the
  GitLab Container Registry.
- `backend:deploy` — manual job for `deployment-dev` or `main`; SSHes into the
  droplet, pulls the selected image, restarts one container, and checks
  `/healthz`.

Image tags:

```text
$CI_REGISTRY_IMAGE/backend:$CI_COMMIT_SHA
$CI_REGISTRY_IMAGE/backend:$CI_COMMIT_REF_SLUG
$CI_REGISTRY_IMAGE/backend:deployment-dev   # only on deployment-dev
$CI_REGISTRY_IMAGE/backend:main             # only on main
$CI_REGISTRY_IMAGE/backend:latest           # only on main
```

Set these GitLab CI/CD variables before using the manual deploy job:

| Variable | Example | Notes |
|---|---|---|
| `DEPLOY_HOST` | `203.0.113.10` | Droplet IP or DNS name. |
| `DEPLOY_USER` | `deploy` | SSH user; defaults to `deploy` in CI. |
| `DEPLOY_SSH_PRIVATE_KEY` | `<private key>` | Private key for the deploy user. Store masked/protected where possible. |
| `DEPLOY_SSH_PORT` | `22` | Optional override. |
| `DEPLOY_BACKEND_ENV_PATH` | `/opt/qtw/backend.env` | Optional override; must exist on the droplet. |

The deploy job uses `deploy/backend-deploy.sh` on the droplet. The script:

- Pulls the CI-built image.
- Restarts container `qtw-backend` with `--restart unless-stopped`.
- Reads runtime env from `/opt/qtw/backend.env`.
- Publishes the container only on `127.0.0.1:8000`.
- Checks `http://127.0.0.1:8000/healthz`.
- Rolls back to the previous image if the new container fails health checks.

### Droplet Bootstrap

Provision the droplet once:

```bash
sudo apt-get update
sudo apt-get install -y docker.io caddy curl
sudo useradd --create-home --shell /bin/bash deploy
sudo usermod -aG docker deploy
sudo install -d -m 755 /opt/qtw
sudo install -m 600 /dev/null /opt/qtw/backend.env
sudoedit /opt/qtw/backend.env
sudo chown root:root /opt/qtw/backend.env
sudo chmod 600 /opt/qtw/backend.env
```

Use `backend/.env.example` as the template for `/opt/qtw/backend.env`; fill in
the real `DATABASE_URL` and `DWAVE_API_TOKEN` on the droplet.

Copy `deploy/Caddyfile.example` to `/etc/caddy/Caddyfile`, then reload Caddy:

```bash
sudo systemctl reload caddy
```

DNS must point `api.qtw.quip.network` at the droplet before Caddy can issue TLS.

## First Production Shape

Recommended first production shape:

```text
Netlify React frontend
  -> DigitalOcean FastAPI container, one Uvicorn worker
      -> Supabase Postgres
      -> assets-api at https://asset-tracker.quip.network
      -> Proton SMTP
      -> D-Wave when DWAVE_API_TOKEN and budget allow
```

Use one backend container and one Uvicorn worker initially because the websocket
bus and MTM scheduler are in-process. One worker still supports many phone
websocket connections; retune/optimization concurrency should be controlled by
rate limits and a solve semaphore.
