# Environment Configuration

This project has three runtime surfaces:

- Netlify hosts the React frontend in `mvp/`.
- A long-lived backend container hosts FastAPI, likely on a DigitalOcean droplet.
- Supabase hosts Postgres only. The browser should never connect to Postgres.

## Local Defaults

With no production env vars set:

- Frontend uses mock API data unless `VITE_API_BASE` is set.
- Backend uses in-memory stores unless `DATABASE_URL` is set.
- Backend uses `assets-api` by default for market data.
- Tests force in-memory stores and synthetic market data.

## Frontend Env - Netlify

Set these in Netlify project environment variables.

| Variable | Required | Example | Notes |
|---|---:|---|---|
| `VITE_API_BASE` | yes for production | `https://api.qtw.quip.network` | Browser HTTP requests to FastAPI. |
| `VITE_WS_BASE` | only if different | `https://api.qtw.quip.network` | Optional. If omitted, frontend derives `ws`/`wss` from `VITE_API_BASE`. |

Do not put database passwords, SMTP tokens, D-Wave tokens, or Supabase service
keys in Netlify frontend env.

## Backend Env - FastAPI Container

Set these on the backend host/container, not in browser-visible env.

| Variable | Required | Example | Notes |
|---|---:|---|---|
| `DATABASE_URL` | production yes | `postgresql+psycopg://postgres:<password>@db.<project>.supabase.co:5432/postgres` | Enables Supabase/Postgres persistence. Unset means in-memory. |
| `APP_ENV` | recommended | `production`, `booth`, `local` | Stored with DB rows so local/test rows can be cleaned up. |
| `QR_BASE_URL` | recommended | `https://qtw.quip.network` | Base for generated phone profile QR URLs. |
| `ASSETS_API_BASE_URL` | recommended | `https://asset-tracker.quip.network` | Market-data service consumed by backend. |
| `MARKET_DATA_SOURCE` | optional | `assets-api` or `synthetic` | Use `synthetic` for offline demos/tests. |
| `VALUATION_SNAPSHOT_INTERVAL_S` | optional | `60` | Durable analytics snapshot cadence. Use `0` to disable. |
| `MTM_TICK_S` | optional in future | `30` | Current code default is 3s; align after assets-api spot cadence changes. |
| `GUROBI_IN_RACE` | production recommended | `0` | Gurobi is local/dev only unless deployment has a valid license. |
| `DWAVE_API_TOKEN` | optional | `<Leap token>` | Enables QPU provider. Unset means CPU-only field. |
| `DWAVE_NUM_READS` | optional | `500` | D-Wave read count. |
| `DWAVE_ANNEAL_TIME_US` | optional | `100` | D-Wave anneal time. |
| `DWAVE_CHAIN_STRENGTH_PREFACTOR` | optional | `3.0` | D-Wave chain strength prefactor. |
| `ASSETS_API_RETRIES` | optional | `2` | Retry count for transient assets-api transport failures. |
| `ASSETS_API_RETRY_BACKOFF_S` | optional | `0.25` | Linear retry backoff. |
| `MTM_ERROR_LOG_INTERVAL_S` | optional | `30` | Throttles repeated MTM failure logs. |

## Supabase/Postgres

Use the direct Postgres connection string for the backend container. Store it as
`DATABASE_URL` only on the backend host.

If using a single Supabase project for local and production:

- Run local DB tests with `APP_ENV=local`.
- Run booth/prod with `APP_ENV=production` or `APP_ENV=booth`.
- Clean up local/test rows by filtering on `environment`.
- Back up/export before booth day.

Local backend with `DATABASE_URL` set writes to Supabase. Local backend with
`DATABASE_URL` unset uses in-memory stores and does not write to Supabase.

## Proton SMTP

Email sending is backend-only. Supabase stores email/consent; FastAPI sends
through Proton SMTP.

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

## First Production Shape

Recommended first deployment:

```text
Netlify React frontend
  -> DigitalOcean FastAPI container, one Uvicorn worker
      -> Supabase Postgres
      -> assets-api
      -> Proton SMTP
      -> D-Wave when token/budget allow
```

Use one backend container and one Uvicorn worker initially because the websocket
bus and MTM scheduler are in-process. One worker still supports many phone
websocket connections; retune/optimization concurrency should be controlled by
rate limits and a solve semaphore.
