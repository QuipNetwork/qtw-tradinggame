# Environment Configuration

This project has three runtime surfaces:

- Netlify hosts the React frontend in `mvp/`.
- A long-lived backend process hosts FastAPI, likely inside a container on a
  DigitalOcean droplet once containerization is added.
- Supabase hosts Postgres only. The browser should never connect to Postgres.

## Local Defaults

With no production env vars set:

- Frontend uses mock API data unless `VITE_API_BASE` is set.
- Backend uses in-memory stores unless `DATABASE_URL` is set.
- Backend uses `assets-api` by default for market data.
- Backend points at `https://asset-tracker.quip.network` by default.
- Tests force in-memory stores and synthetic market data.
- Email sending is not wired yet; signup currently stores email/consent only.
- The backend is not containerized yet; there is no `Dockerfile`,
  `docker-compose.yml`, or DigitalOcean app spec in this repo.

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

| Variable | Required | Example | Notes |
|---|---:|---|---|
| `DATABASE_URL` | yes | `postgresql://postgres.<project-ref>:<password>@aws-1-us-west-2.pooler.supabase.com:5432/postgres` | Enables Supabase/Postgres persistence. Use the Supabase pooler when direct IPv6 DB host is not reachable. |
| `APP_ENV` | yes | `production`, `booth`, `local-smoke-azain` | Stored with DB rows so local/test rows can be cleaned up safely. |
| `QR_BASE_URL` | yes | `https://qtw.quip.network` | Base for generated phone profile QR URLs. |
| `ASSETS_API_BASE_URL` | yes | `https://asset-tracker.quip.network` | Market-data service consumed by backend. |
| `DWAVE_API_TOKEN` | yes for QPU booth mode | `<Leap token>` | Enables D-Wave/QPU participation. Without it, the D-Wave provider is omitted. |
| `GUROBI_IN_RACE` | yes | `0` | Keep `0` in production; Gurobi is local/dev only unless deployment has a valid license. |
| `VALUATION_SNAPSHOT_INTERVAL_S` | no | `60` | Durable analytics snapshot cadence. Use `0` to disable snapshots. |

`MARKET_DATA_SOURCE` defaults to `assets-api`, so production usually does not
need to set it. Set `MARKET_DATA_SOURCE=synthetic` only for offline demos or
debugging without real market data.

D-Wave tuning knobs such as `DWAVE_NUM_READS`, `DWAVE_ANNEAL_TIME_US`, and
`DWAVE_CHAIN_STRENGTH_PREFACTOR` have code defaults. Do not put them in the
normal production env unless you are deliberately running a hardware tuning
pass.

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

delete from valuation_snapshots where environment = 'local-smoke-azain';
delete from solve_snapshots where environment = 'local-smoke-azain';
delete from jobs where environment = 'local-smoke-azain';
delete from agent_holdings where environment = 'local-smoke-azain';
delete from agents where environment = 'local-smoke-azain';

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

Status: not implemented yet.

The repo currently has no backend `Dockerfile`, `Containerfile`, compose file,
or CI deploy workflow. Local/server execution is still direct Python:

```bash
cd backend
.venv/bin/python -m uvicorn backend.api.app:app --workers 1 --port 8001
```

Chosen production path: **DigitalOcean droplet + Docker**.

Containerization should add, at minimum:

- `backend/Dockerfile` or root `Dockerfile.backend`
- `.dockerignore`
- a production command that binds publicly inside the container:

```bash
uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --workers 1
```

The one-worker constraint is intentional for the first deployment. The websocket
event bus, MTM scheduler, and scheduled rebalance loop are in-process. More than
one worker/container would need an external event bus plus scheduler locking.

The deploy loop should be:

- Build an AMD64 backend image from the chosen deployment branch.
- Push the image to a container registry.
- Pull and restart that image on the droplet, either manually at first or via CI
  over SSH.
- Terminate TLS on the droplet with Caddy/Nginx/Traefik for
  `api.qtw.quip.network`, proxying traffic to the FastAPI container.

## First Production Shape

Recommended first deployment after containerization:

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
