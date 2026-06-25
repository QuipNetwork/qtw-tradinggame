# QTW Backend Deploy Runbook

This is the single operator document for deploying the QTW FastAPI backend,
setting runtime environment variables, wiring the Netlify frontend, configuring
Supabase/Postgres, and enabling Resend email.

Backend dataflow: `docs/BACKEND_DAG.md`.
CI pipeline: `.gitlab-ci.yml`.
Deploy script: `deploy/backend-deploy.sh`.
Caddy example: `deploy/Caddyfile.example`.

## Target Shape

```text
Netlify frontend: https://qtw.quip.network
  VITE_API_BASE=https://qtw.backend.quip.network
  VITE_WS_BASE unset unless websocket traffic uses a different host
        |
        v
Caddy on DigitalOcean droplet, ports 80/443
        |
        v
Docker container: qtw-backend, Uvicorn, one worker, 127.0.0.1:8000
        |
        +-> Supabase Postgres through DATABASE_URL
        +-> assets-api at https://asset-tracker.quip.network
        +-> D-Wave Leap when DWAVE_API_TOKEN is set
        +-> Resend email API when RESEND_API_KEY is set
```

Run one backend container with one Uvicorn worker for the first production
deployment. The websocket bus, MTM scheduler, scheduled rebalance loop, and
solve queue are in-process.

## What Goes Where

| Surface | Put There | Never Put There |
|---|---|---|
| Netlify frontend env | `VITE_API_BASE`, optional `VITE_WS_BASE` | Database URLs, the Resend key, D-Wave tokens, Supabase service keys |
| Droplet `/opt/qtw/backend.env` | Backend runtime env and secrets | Browser-visible values only |
| GitLab CI/CD variables | Deploy SSH settings | Runtime app secrets unless they are needed by CI |
| Supabase | Postgres data only | Browser direct access |

## Operator Checklist

1. Provision a DigitalOcean Ubuntu droplet.
2. Point `qtw.backend.quip.network` DNS to the droplet.
3. Install Docker, Caddy, and curl.
4. Create `/opt/qtw/backend.env`.
5. Fill backend env values and secrets.
6. Create `/etc/caddy/Caddyfile`.
7. Set GitLab deploy variables.
8. Run the manual GitLab `backend:deploy` job.
9. Set Netlify `VITE_API_BASE=https://qtw.backend.quip.network`.
10. Redeploy Netlify.
11. Run the production smoke tests below.

## Droplet Bootstrap

Run once on the DigitalOcean droplet:

```bash
sudo apt-get update
sudo apt-get install -y docker.io caddy curl

sudo useradd --create-home --shell /bin/bash deploy
sudo usermod -aG docker deploy

sudo install -d -m 755 /opt/qtw
sudo install -m 640 -o root -g deploy /dev/null /opt/qtw/backend.env
sudoedit /opt/qtw/backend.env
sudo chmod 640 /opt/qtw/backend.env
```

Add the CI deploy public key to:

```text
/home/deploy/.ssh/authorized_keys
```

If a firewall is enabled:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

The env file is `root:deploy` with mode `640` so the deploy user can run Docker
with `--env-file /opt/qtw/backend.env`.

## Backend Runtime Env

Create `/opt/qtw/backend.env` from `backend/.env.example`, then fill real
secrets on the droplet only:

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

## Supabase/Postgres

Store `DATABASE_URL` only on the backend host/container. The browser and
Netlify frontend must never receive the database password.

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

Restart the backend after cleanup because the running process may still hold the
old working set in memory.

## DNS And Caddy

Point DNS:

```text
qtw.backend.quip.network A <droplet-ip>
```

Create `/etc/caddy/Caddyfile` from `deploy/Caddyfile.example`. The core proxy
shape is:

```caddy
qtw.backend.quip.network {
	encode zstd gzip
	reverse_proxy 127.0.0.1:8000
}
```

Reload Caddy:

```bash
sudo systemctl reload caddy
```

Caddy can issue TLS only after DNS resolves to the droplet and ports `80/443`
are open. The backend container binds to `127.0.0.1:8000`; public traffic should
enter through Caddy.

## GitLab CI/CD Variables

Set these in GitLab project settings:

| Variable | Required | Example |
|---|---:|---|
| `DEPLOY_HOST` | yes | `203.0.113.10` or `qtw.backend.quip.network` |
| `DEPLOY_SSH_PRIVATE_KEY` | yes | Private key matching the droplet deploy public key |
| `DEPLOY_USER` | no | `deploy` |
| `DEPLOY_SSH_PORT` | no | `22` |
| `DEPLOY_BACKEND_ENV_PATH` | no | `/opt/qtw/backend.env` |
| `DEPLOY_BACKEND_HEALTH_URL` | no | `http://127.0.0.1:8000/healthz` |

GitLab provides `CI_REGISTRY`, `CI_REGISTRY_IMAGE`, `CI_REGISTRY_USER`, and
`CI_REGISTRY_PASSWORD` automatically for image build and droplet pull.

## Deploy

1. Push to `deployment-dev` or `main`.
2. Let `backend:test` and `backend:image` pass.
3. Manually run `backend:deploy`.
4. Confirm the deploy job reports a healthy backend.

Useful droplet checks:

```bash
docker ps
docker logs --tail 120 qtw-backend
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS https://qtw.backend.quip.network/healthz
```

Expected `/healthz` in production:

```json
{
  "appEnv": "production",
  "persistence": "sql",
  "marketDataSource": "assets-api",
  "qpuConfigured": true,
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

Redeploy Netlify after env changes because Vite bakes `VITE_*` variables at
build time.

## Email (Resend)

Transactional email goes through **Resend's HTTPS API** (port 443). DigitalOcean
blocks outbound SMTP from the droplet (25/465/587 all time out), so SMTP — Proton
or any relay on the standard ports — is not viable; Resend's API is the reliable
sender.

Current behavior:

- Email sends only from the FastAPI backend container.
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
3. Add to `/opt/qtw/backend.env` (backend-only — never commit, never put in Netlify):

```bash
RESEND_API_KEY=<Resend API key>
EMAIL_FROM=Quip Network <noreply@quip.network>
```

Do not commit the key. If it was shared outside the production secret store,
rotate it in the Resend dashboard before the final production deploy.

To disable email, leave `RESEND_API_KEY` unset — the backend falls back to the
no-op provider (logs only, no send).

## Applying Env Changes

Recreate the backend container after editing `/opt/qtw/backend.env`.

Preferred path:

1. Push the current branch.
2. Let GitLab build the backend image.
3. Run the manual `backend:deploy` job.

Important: `docker restart qtw-backend` is not enough. Docker reads
`--env-file /opt/qtw/backend.env` when the container is created, not on restart.

If you need to recreate the container manually with the currently running image:

```bash
IMAGE="$(docker inspect --format '{{.Config.Image}}' qtw-backend)"
docker rm -f qtw-backend
docker run -d \
  --name qtw-backend \
  --restart unless-stopped \
  --env-file /opt/qtw/backend.env \
  -p 127.0.0.1:8000:8000 \
  "$IMAGE"
```

## Email Smoke Test

Check startup logs:

```bash
docker logs --tail 120 qtw-backend | grep -E "email provider"
```

Expected startup log shape:

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
- If Resend rejects the send, signup still returns `200`; check
  `docker logs --tail 120 qtw-backend` for the stack trace (a 403 usually means
  the `quip.network` domain is not verified in Resend).

The health endpoint does not expose email status by design. Use logs and the
smoke-test email for delivery confirmation.

## Production Smoke Test

After backend and frontend are connected:

1. Open `https://qtw.quip.network`.
2. Create an agent from the kiosk flow.
3. Confirm the QR URL points to `https://qtw.quip.network/p/{agentId}`.
4. Run an optimization and confirm the phone receives websocket updates.
5. Confirm Supabase has rows with `environment='production'`.
6. Restart by recreating the backend container and confirm the agent/leaderboard
   hydrate from DB.
7. Confirm `valuation_snapshots` are sampled around every 60 seconds, not every
   MTM tick.
8. If email is enabled, confirm an opted-in signup receives the confirmation email.

## Troubleshooting

- Deploy job fails before SSH: check `DEPLOY_HOST`, `DEPLOY_SSH_PRIVATE_KEY`,
  deploy public key, and droplet firewall.
- Deploy job fails at `--env-file`: confirm `/opt/qtw/backend.env` exists and is
  readable by the `deploy` user.
- `/healthz` returns `persistence: "memory"`: `DATABASE_URL` is missing or not
  loaded in the running container.
- Caddy cannot issue TLS: confirm `qtw.backend.quip.network` resolves to the
  droplet and ports `80/443` are open.
- Frontend still hits mocks: confirm Netlify has `VITE_API_BASE` set and the
  site was rebuilt after setting it.
- QPU does not appear: confirm `DWAVE_API_TOKEN` is present in backend env and
  the container was recreated after editing env.
- Email provider remains `noop`: confirm `RESEND_API_KEY` is set and the container
  was recreated after editing env.
- Email does not arrive: confirm the `quip.network` domain is verified in Resend,
  check the startup `email provider: resend` log, and backend logs for the send
  stack trace.

## Remaining Deployment Work

- Provision the DigitalOcean droplet.
- Point DNS for `qtw.backend.quip.network`.
- Create `/opt/qtw/backend.env` with production secrets.
- Set GitLab CI/CD deploy variables.
- Run the first manual `backend:deploy` job.
- Set Netlify `VITE_API_BASE` and redeploy.
- Complete a Supabase-backed smoke test.
- Add hourly/daily scheduled result emails if booth email cadence is required
  beyond the initial signup confirmation.
