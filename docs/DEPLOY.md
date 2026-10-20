# QTW Backend Deploy Runbook

This is the single operator document for deploying the QTW FastAPI backend,
setting runtime environment variables, wiring the Netlify frontend, configuring
Supabase/Postgres, and enabling Resend email.

Backend dataflow: `docs/BACKEND_DAG.md`.
CI pipeline: `.gitlab-ci.yml`.
Retired DigitalOcean deploy (June–July 2026): `docs/DEPLOY-DO-HISTORICAL.md`.
Orbit migration record: Linear QUI-875 and QUI-876.

## Target Shape

```text
Netlify frontend: https://qtw.quip.network
  VITE_API_BASE=https://qtw.backend.quip.network
  VITE_WS_BASE unset unless websocket traffic uses a different host
        |
        v
Flux load balancer: qtw.backend.quip.network -> qtw-backend.app.runonflux.io
        |
        v
Flux Orbit app "qtw-backend", one instance
  builds the deploy/orbit branch, Uvicorn, one worker, port 8000
        |
        +-> Supabase Postgres through DATABASE_URL
        +-> assets-api at https://asset-tracker.quip.network
        +-> D-Wave Leap when DWAVE_API_TOKEN is set
        +-> Quip testnet (Aglais) when XQUAD_BACKEND=quip
        +-> Resend email API when RESEND_API_KEY is set
```

Run one instance with one Uvicorn worker. The websocket bus, MTM scheduler,
scheduled rebalance loop, solve queue, and Quip order queue are in-process.

## What Goes Where

| Surface | Put There | Never Put There |
|---|---|---|
| Netlify frontend env | `VITE_API_BASE`, optional `VITE_WS_BASE` | Database URLs, the Resend key, D-Wave tokens, Quip seeds, Supabase service keys |
| Flux Orbit app env (encrypted) | Backend runtime env and secrets | Browser-visible values only |
| `deploy/orbit` branch | The code Orbit builds, `backend/requirements.txt` pins | Secrets |
| GitLab CI/CD variables | Nothing for deploy | Runtime app secrets |
| Supabase | Postgres data only | Browser direct access |

## Deploy

The backend runs as a single-instance Flux Orbit app named `qtw-backend`. Orbit
clones this repository's `deploy/orbit` branch and builds it on the Flux node;
no container registry image is involved. The app settings recorded in QUI-875:

```text
PROJECT_PATH=backend
APP_PORT=8000
RUN_COMMAND=/opt/flux-tools/conda/bin/uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --workers 1
```

Orbit installs Python dependencies from the first file it finds in
`backend/`: `uv.lock`, then `requirements.txt`, then `pyproject.toml`.
`deploy/orbit` carries a pinned `backend/requirements.txt` (captured from the
retired droplet's container) and a `backend/.python-version` of `3.12`, and no
`uv.lock`. Its last line, `.`, installs the backend package itself.

`deploy/orbit` is not `main`. It branched from `main` at `3d6acc6` (2026-06-26)
and adds two commits: `93b1db9` (the send-off email variant that was deployed)
and `6e66183` (the Python pin and `requirements.txt`). Everything merged to
`main` after June 26 is not deployed; see Deploying Main To Orbit.

To deploy a change:

1. Update `deploy/orbit` with the commit to run.
2. In the Flux Cloud console, run a **Hard Redeploy** of `qtw-backend`.
3. Watch the app logs for startup, then run the smoke tests below.

Always use Hard Redeploy. The Python environment is per container while the
packaged release persists, so a plain redeploy or restart brings the app back
without its dependencies and it crash-loops with exit code 127.

Orbit redeploys on new commits only when the app sets `POLLING_INTERVAL` or a
`WEBHOOK_SECRET` with a webhook pointed at it. The `qtw-backend` app
specification is encrypted, so this cannot be read from the public Flux API, and
the GitLab project has no Orbit webhook. Until someone with access to the Flux
app confirms its settings, do not rely on a push to deploy, and do not push
anything to `deploy/orbit` that you are not ready to run.

CI does not deploy. `.gitlab-ci.yml` runs the backend tests and builds and
pushes `registry.gitlab.com/quip.network/qtw-tradinggame/backend` images, which
the Orbit app does not use.

`/healthz` does not contact external services, so a healthy deploy does not
prove that assets-api, Postgres, or the Quip RPC are reachable; check the
startup logs (`assets-api reachable at …`) and run the smoke tests below.

Health checks:

```bash
curl -fsS https://qtw.backend.quip.network/healthz
curl -fsS https://qtw-backend.app.runonflux.io/healthz
```

The second URL is the Flux app domain and bypasses the custom hostname.

## Deploying Main To Orbit

Not done yet. Until it is, the frontend on `main` runs against an older backend:
`deploy/orbit` has no `GET /agents/{id}/latest-result`, so a phone shows no
race until it retunes, and it accepts the agent token only as `?t=`, so the
phone's websocket, which sends the token as a subprotocol, is rejected and the
phone gets no live updates. Deploy `main` to Orbit before or together with the
Netlify build of the same commit.

Moving `main` onto `deploy/orbit` takes:

1. **Send-off email.** Decide whether `93b1db9`'s send-off variant
   (`backend/src/backend/notifications/seeoff.py`) belongs on `main`. Building
   `deploy/orbit` from `main` without it replaces the deployed variant with
   `main`'s.
2. **Python version.** Set `backend/.python-version` to `3.13`. `main`'s
   `pyproject.toml` and `uv.lock` require Python `>=3.13`, and CI and the
   Dockerfile use 3.13; the current `3.12` pin cannot install it.
3. **Dependencies.** `main` tracks `backend/uv.lock`, which Orbit would prefer
   over `requirements.txt`. Regenerate the pins from the lock, keep the trailing
   `.` line, and leave `uv.lock` off `deploy/orbit`:

   ```bash
   cd backend
   uv export --format requirements-txt --frozen --no-dev --no-hashes --no-emit-project > requirements.txt
   printf '\n.\n' >> requirements.txt
   git rm uv.lock
   ```

   Check that `requirements.txt` pins `xqsa==0.4.4`. Since Aglais runtime 119,
   xqsa 0.4.2 and earlier cannot place Quip orders, so every Quip row would
   fail.
4. **Quip env.** With `XQUAD_BACKEND=quip`, add `QUIP_SIGNER_SEED` to the Orbit
   app env; the server refuses to start without it. `XQUAD_TIMEOUT_S` defaults to
   180 s in code and needs no entry; remove one left in the app env, since a
   `120` or `300` overrides the default. Leave `XQUAD_BACKEND` unset to keep Quip
   orders off.
5. **Tag the rollback target.** The result is built on `main`, and
   `deploy/orbit`'s two commits are not on `main`, so moving the branch is a
   force-push that leaves `6e66183` unreferenced. Tag it first so it cannot be
   garbage-collected:

   ```bash
   git tag orbit-2026-07-27 6e66183
   git push origin orbit-2026-07-27
   ```

6. **Deploy.** Force-push the result to `deploy/orbit` (the branch is not
   protected; if it becomes protected, allow force push on it first), run a
   Hard Redeploy, and run the smoke tests. Until the Netlify frontend sends the
   websocket token as a subprotocol, roll back by force-pushing
   `orbit-2026-07-27` to `deploy/orbit` and running a Hard Redeploy. Once it
   does, roll back only to a commit that accepts the subprotocol token: an older
   backend rejects the phone's websocket, and the page shows no error.

## Backend Runtime Env

Set backend env in the Orbit app's encrypted environment, using
`backend/.env.example` as the reference. Never commit real values:

```bash
APP_ENV=production
QR_BASE_URL=https://qtw.quip.network
ASSETS_API_BASE_URL=https://asset-tracker.quip.network
GUROBI_IN_RACE=0
MTM_TICK_S=10
VALUATION_SNAPSHOT_INTERVAL_S=60
QPU_BUDGET_MAX_ATTEMPTS=8
QPU_BUDGET_WINDOW_S=600

DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-1-us-west-2.pooler.supabase.com:5432/postgres
DWAVE_API_TOKEN=<Leap token>

RESEND_API_KEY=<Resend API key>
EMAIL_FROM=Quip Network <noreply@quip.network>
```

The Orbit app env was pruned during the move (QUI-875): `DWAVE_API_TOKEN` was
removed deliberately, so the deployed backend runs without the QPU, and
variables that duplicated a code default were dropped.

`MARKET_DATA_SOURCE` defaults to `assets-api`; set
`MARKET_DATA_SOURCE=synthetic` only for offline demos or debugging without real
market data.

D-Wave tuning knobs such as `DWAVE_NUM_READS`, `DWAVE_ANNEAL_TIME_US`, and
`DWAVE_CHAIN_STRENGTH_PREFACTOR` have code defaults. Do not put them in normal
production env unless deliberately running a hardware tuning pass.

## Runtime Env Reference

| Variable | Required | Example | Notes |
|---|---:|---|---|
| `APP_ENV` | yes | `production`, `booth` | Production/booth require `DATABASE_URL`; value is stored with rows for cleanup. |
| `DATABASE_URL` | yes | Supabase pooler URL | Enables SQL-backed persistence. Keep backend-only. |
| `QR_BASE_URL` | yes | `https://qtw.quip.network` | Base URL for generated phone profile links. |
| `ASSETS_API_BASE_URL` | yes | `https://asset-tracker.quip.network` | Market-data service consumed by backend. |
| `DWAVE_API_TOKEN` | yes for QPU booth mode | `<Leap token>` | Enables D-Wave/QPU participation. |
| `GUROBI_IN_RACE` | yes | `0` | Keep `0` in production; Gurobi is local/dev unless a valid license is deployed. |
| `MTM_TICK_S` | no | `10` | Backend mark-to-market/websocket cadence; default matches assets-api spot cadence. |
| `VALUATION_SNAPSHOT_INTERVAL_S` | no | `60` | Durable valuation history snapshot cadence. Use `0` to disable. |
| `QPU_BUDGET_MAX_ATTEMPTS` | no | `3` | Production booth override: per-agent QPU-admitted solves per rolling window. Code fallback is `8`. |
| `QPU_BUDGET_WINDOW_S` | no | `600` | QPU budget window in seconds. |
| `RESEND_API_KEY` | yes for email | `<Resend API key>` | Registers the Resend (HTTPS) email provider at startup. If unset, email stays no-op. |
| `EMAIL_FROM` | yes for email | `Quip Network <noreply@quip.network>` | Display sender; must be an address on a Resend-verified domain. |
| `RESEND_TIMEOUT_S` | no | `10` | Resend API request timeout. |
| `XQUAD_BACKEND` | no | `quip` | Unset/`off` keeps the direct D-Wave solver. `quip` also sends each manual solve to the Quip testnet as a background order; see Quip Testnet Orders. |
| `QUIP_SIGNER_SEED` | yes with `XQUAD_BACKEND=quip` | 32-byte hex seed | The Quip signing account. Or set `QUIP_KEYSTORE` instead. |
| `QUIP_KEYSTORE` | alternative to the seed | `/data/quip/keystore.json` | Keystore path inside the app; the Orbit deploy provides env vars only, so use the seed there. |
| `XQUAD_TIMEOUT_S` | no | `180` | How long the worker waits for one Quip order to finalize. |
| `QUIP_MAX_PENDING_ORDERS` | no | `3` | Orders queued or in flight at once; extra solves record the Quip row as `skipped`. |
| `QUIP_RPC_URL` | no | unset | Unset uses xqsa's `aglais` preset (public RPC and faucet). Set only for another node. |
| `QUIP_AUTOFUND` | no | `1` | `0` stops the faucet top-up when the account cannot cover an order. |

## Applying Env Changes

Edit the env in the Orbit app settings, then run a **Hard Redeploy**. A restart
or plain redeploy does not apply env changes and leaves the app without its
Python dependencies (see Deploy).

## Supabase/Postgres

Store `DATABASE_URL` only in the Orbit app env. The browser and Netlify frontend
must never receive the database password.

Prefer the Supabase session pooler on port `5432`:

```text
postgresql://postgres.<project-ref>:<password>@aws-1-us-west-2.pooler.supabase.com:5432/postgres
```

The direct Supabase host may fail from networks without IPv6 support:

```text
postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
```

If using one Supabase project for local and production:

- Run local DB tests with `APP_ENV=local` or `APP_ENV=local-smoke-azain`.
- Run booth/prod with `APP_ENV=production` or `APP_ENV=booth`.
- Clean up local/test rows by filtering on `environment`.
- Back up/export before booth day.

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

Redeploy the backend after cleanup because the running process may still hold
the old working set in memory.

## Quip Testnet Orders

Optional, and not available on the deployed `deploy/orbit` code (see Deploying
Main To Orbit). With `XQUAD_BACKEND=quip`, each manual solve also proposes an
order on the Quip testnet (Aglais) from a background worker. The local solver
race decides the portfolio; the Quip result only fills in that solve's
`xquad-quip` row later, and never changes holdings. Scheduled rebalances do not
send orders. Each order reserves about 1 AGLS reward plus a fee from the signing
account, topped up from the public faucet when short.

Give the backend one stable signing account by setting `QUIP_SIGNER_SEED` in the
Orbit app env; without one, every redeploy would sign from a fresh empty
account. The server refuses to start with `XQUAD_BACKEND=quip` and neither
`QUIP_SIGNER_SEED` nor `QUIP_KEYSTORE` set. The Quip queue is in memory: a
redeploy drops queued orders, and any result still `pending` is marked `failed`
at the next startup.

Expected `/healthz` from the Orbit app (`qpuConfigured` is `false` while
`DWAVE_API_TOKEN` is unset):

```json
{
  "status": "ok",
  "appEnv": "production",
  "persistence": "sql",
  "marketDataSource": "assets-api",
  "assetsApiBaseUrl": "https://asset-tracker.quip.network",
  "qpuConfigured": false,
  "gurobiInRace": false
}
```

## Netlify Frontend

Set this in Netlify project env:

```bash
VITE_API_BASE=https://qtw.backend.quip.network
```

Usually leave `VITE_WS_BASE` unset; the frontend derives websocket URLs from
`VITE_API_BASE`. Set it only if websocket traffic uses a different host.

The agent websocket sends the owner token in the `Sec-WebSocket-Protocol`
request header (`quip.v1`, `auth.<token>`), since browsers cannot set other
websocket headers and a query string would be logged. Any proxy in front of the
backend must forward that header, and must not write it to an access log.

Redeploy Netlify after env changes because Vite bakes `VITE_*` variables at
build time.

## Email (Resend)

Transactional email goes through **Resend's HTTPS API** (port 443). The backend
has no SMTP provider; SMTP was ruled out on the retired DigitalOcean droplet,
which blocked outbound 25/465/587.

Current behavior:

- Email sends only from the FastAPI backend.
- Netlify and the browser never receive the Resend key.
- After `POST /agents` persists the attendee, the backend sends a signup
  confirmation to anyone who provided an email. It carries the attendee's secure
  agent link (`/p/{id}#t={token}`); when they did not opt into result emails it
  also states the link is one-time and no further mail will follow.
- Opted-in attendees (`updatesOptIn=true`) also receive a portfolio-result email
  after a rebalance, throttled to their cadence (`updateFrequency`: hourly = at
  most 1/h, daily = at most 1/24h). The result email is informational only — the
  secure deep link lives solely in the signup email, because only the token hash
  is stored server-side.
- Resend send failures are logged and do not fail signup or a rebalance.
- Note: the signup link puts the capability token in an email (TLS in transit +
  the recipient inbox), a conscious tradeoff vs. the log-safe URL-fragment design
  — acceptable for a short-lived, play-money booth agent.

Setup:

1. Create a Resend account and a **send-only** API key.
2. Verify the `quip.network` domain in Resend (add the DKIM + SPF DNS records it
   issues) so you can send from `noreply@quip.network`.
3. Add to the Orbit app env (backend-only — never commit, never put in Netlify),
   then Hard Redeploy:

```bash
RESEND_API_KEY=<Resend API key>
EMAIL_FROM=Quip Network <noreply@quip.network>
```

Do not commit the key. If it was shared outside the production secret store,
rotate it in the Resend dashboard.

To disable email, leave `RESEND_API_KEY` unset — the backend falls back to the
no-op provider (logs only, no send).

## Email Smoke Test

Check the startup lines in the Orbit app logs for:

```text
email provider: resend from=Quip Network <noreply@quip.network>
```

Send a test signup to a real inbox you control:

```bash
curl -fsS -X POST https://qtw.backend.quip.network/agents \
  -H 'content-type: application/json' \
  --data '{
    "name": "Email Smoke",
    "email": "<test-inbox@example.com>",
    "updatesOptIn": true,
    "updateFrequency": "daily",
    "sliders": {
      "rebalanceFrequency": 50,
      "riskPreference": 70,
      "maxPositionSize": 50
    },
    "assets": [
      "BTC", "ETH", "SOL", "USDC", "IONQ",
      "QBTS", "RGTI", "IBM", "GOOGL", "NVDA",
      "MSFT", "AMZN", "HON", "SAF", "SPCX"
    ]
  }'
```

Expected result:

- The API returns `200`.
- The test inbox receives a QTW signup confirmation from
  `Quip Network <noreply@quip.network>`.
- If Resend rejects the send, signup still returns `200`; check the Orbit app
  logs for the stack trace (a 403 usually means the `quip.network` domain is not
  verified in Resend).

The health endpoint does not expose email status by design. Use logs and the
smoke-test email for delivery confirmation.

## Production Smoke Test

After backend and frontend are connected:

1. Open `https://qtw.quip.network`.
2. Create an agent from the kiosk flow.
3. Confirm the QR URL points to `https://qtw.quip.network/p/{agentId}`.
4. Run an optimization and confirm the phone receives websocket updates. With
   `XQUAD_BACKEND=quip`, confirm the phone's Quip row goes from "on chain…" to
   its final status and order ID without a reload.
5. Confirm Supabase has rows with `environment='production'`.
6. Hard Redeploy the Orbit app and confirm the agent/leaderboard hydrate from DB.
7. Confirm `valuation_snapshots` are sampled around every 60 seconds, not every
   MTM tick.
8. If email is enabled, confirm an opted-in signup receives the confirmation email.

## Troubleshooting

- App crash-loops with exit code `127` after a redeploy: it was a plain
  redeploy or restart; run a Hard Redeploy.
- Build fails resolving dependencies: check which of `uv.lock`,
  `requirements.txt`, or `pyproject.toml` Orbit used, and that
  `backend/.python-version` satisfies the project's `requires-python`.
- App exits at startup with `XQUAD_BACKEND=quip requires …`: set
  `QUIP_SIGNER_SEED` in the Orbit app env, or unset `XQUAD_BACKEND`.
- Quip rows stay `failed` or `timeout`: search the app logs for `quip order`;
  the testnet RPC or faucet may be down, and https://aglais.quip.network lists
  the current endpoints. Every order failing right after a deploy means an xqsa
  older than 0.4.3 (see Deploying Main To Orbit).
- The first Quip order after about two minutes without one fails with `could not
  read the QuantumComputeMempool.MaxNodes constant`: the Aglais RPC closes a
  websocket after about 120 s without traffic, and the worker reused the closed
  connection. The worker then reconnects, so the next order goes through.
- The phone loads but never updates live: the backend is older than the
  frontend and rejects the subprotocol token (see Deploying Main To Orbit).
- `/healthz` returns `persistence: "memory"`: `DATABASE_URL` is missing from the
  Orbit app env, or the app was not Hard Redeployed after adding it.
- `qtw.backend.quip.network` fails while `qtw-backend.app.runonflux.io` answers:
  check the `qtw.backend.quip.network` DNS record, which points at
  `qtw-backend.app.runonflux.io`.
- Frontend still hits mocks: confirm Netlify has `VITE_API_BASE` set and the
  site was rebuilt after setting it.
- QPU does not appear: `DWAVE_API_TOKEN` is not set in the Orbit app env, which
  is the current deliberate state.
- Email provider remains `noop`: confirm `RESEND_API_KEY` is set and the app
  was Hard Redeployed after editing env.
- Email does not arrive: confirm the `quip.network` domain is verified in Resend,
  check the startup `email provider: resend` log, and the app logs for the send
  stack trace.

## Remaining Deployment Work

- Deploy `main` to Orbit (see Deploying Main To Orbit).
- Confirm whether the `qtw-backend` app sets `POLLING_INTERVAL` or a webhook,
  and record the answer in Deploy.
- Check what Flux's load balancer does in front of the app. The retired Caddy
  proxy (`git show 9de8084:deploy/Caddyfile.example`) capped request bodies
  at 64 KB, added security headers, and overwrote `X-Real-IP`, which the
  signup rate limiter reads first; nothing in this repo does that on Orbit.
  Also confirm that it forwards `Sec-WebSocket-Protocol` and does not log it
  (see Netlify Frontend).
- Decide whether `backend:image` in CI should keep pushing registry images that
  no deploy consumes.
