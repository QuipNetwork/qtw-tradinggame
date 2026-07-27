# Historical: how the DigitalOcean backend was actually deployed (retired 2026-07-27)

**Status: RETIRED.** `qtw.backend.quip.network` moved to Flux Orbit on 2026-07-27 (QUI-875). The
droplet `67.205.187.156` was stopped the same day and is scheduled for destruction. This document
exists because the procedure that actually ran on that box **was never written down**, and the
artifacts proving it disappear with the droplet.

Read this if you need to understand how the image that served production for a month was produced,
or why `docs/DEPLOY.md` and `deploy/backend-deploy.sh` do not describe reality.

> **Confidence.** Everything under "Observed" was read directly off the droplet on 2026-07-26/27
> before it was stopped. Everything under "Reconstructed" is inference from those artifacts — the
> ordering is consistent with all timestamps but **no wrapper script implementing it was ever found
> on the box**. If one existed it lived in shell history, not in the repo. Treat the reconstruction
> as the best available account, not as gospel.

---

## The short version

The repo's `deploy/backend-deploy.sh` describes a **pull-and-restart** deploy. What actually happened
was a **build-on-the-box, stage-a-release, rename-the-old-container** deploy. Three of its steps have
no counterpart in the script, and one step in the script (`docker pull`) could not have worked at all.

---

## Observed: what was on the droplet

### `/opt/qtw/` layout

```
/opt/qtw/
├── backend.env                              0640 root:deploy, 936 B — the ONLY copy of live secrets
├── backend.env.bak-20260625-124645          (note: different timestamp format)
├── backend.env.bak-20260625T063658Z
├── backend.env.bak-20260626T224641Z
├── build/backend/…                          a build-context copy, dated Jun 24
├── releases/
│   ├── 20260625T142048Z-74e8b59/            <UTC timestamp>Z-<short sha>
│   └── 20260626T221628Z-48f080a/            (a third, 20260625T065252Z-150c952, existed earlier and
│                                             had been pruned by 2026-07-27 — so only ~2-3 are kept)
└── src/                                     plain NON-git source copy, dated Jun 24
```

A release directory holds the **full repo tree at that commit** — `backend/`, `deploy/`, `docs/`,
`.gitlab-ci.yml`, `README.md`, `design-doc.html`. Not just the backend subtree.

**There was no `.git` directory anywhere on the box.** `find / -xdev -name .git -maxdepth 10`
returned nothing. So the release trees were exported, not cloned.

### Images — all local, never pushed

```
qtw-backend:48f080a   917 MB on disk / 202 MB content   Created 2026-06-26T22:20:11Z
qtw-backend:74e8b59
qtw-backend:150c952
qtw-backend:cc761f0
qtw-backend:225b94e
```

Tag = the short commit sha, matching the release directory suffix. **Zero registry-namespaced
images** (`docker images --format '{{.Repository}}' | grep /` was empty), and `/root/.docker/` did
not exist, so the box had no registry credentials in either direction. `Config.Labels` was `null` —
no `org.opencontainers.image.revision`, so an image self-attested nothing about its source.

### Containers — retired by rename, not removed

```
qtw-backend                          qtw-backend:48f080a   Up (healthy)
qtw-backend-prev-20260625T065252Z    qtw-backend:cc761f0   Exited (0)
qtw-backend-prev-20260625T063658Z    qtw-backend:cc761f0   Exited (0)
```

### The live container's run configuration

```
--name qtw-backend
--restart unless-stopped
-p 127.0.0.1:8000:8000          loopback only, never 0.0.0.0
--env-file /opt/qtw/backend.env  the ONLY env source (all app vars came from here)
qtw-backend:<short-sha>
```
No volumes (`Mounts: []`). Bridge network. No entrypoint override — `WORKDIR`, `USER appuser`, and
`CMD ["uvicorn","backend.api.app:app","--host","0.0.0.0","--port","8000","--workers","1"]` all came
from the image. No systemd unit and no cron job referenced qtw — liveness was purely Docker's
`--restart unless-stopped`.

### Timestamps from the final deploy (`48f080a`, 2026-06-26)

| Time (UTC) | Event |
|---|---|
| 22:13:54 | file mtimes inside the release tree |
| 22:16:28 | release directory created |
| 22:17:13 | release directory finished populating |
| 22:20:11 | **image built** |
| 22:46:41 | `backend.env.bak-20260626T224641Z` written |
| 22:46:42 | **container started** |

The ~26-minute gap between image build and container start is the strongest evidence this was
**hand-run in stages**, not a single script.

### Proof the release tree was the build input

The `backend/src` Python tree in `releases/20260626T221628Z-48f080a/` was **byte-identical** to the
running container's `/app/backend/src` — 54 files, identical per-file hashes, aggregate
`eb191eb35ab69b2f0056908d1c72ffc5b1f2b4929e0021e4cf18ff1b05dedd5c`.

⚠ Compute that with `LC_ALL=C sort`. The aggregate hash is locale-sensitive — `find | sort` orders
`_` and `/` differently under a non-C locale and reports identical trees as different.

---

## Reconstructed: the procedure

One UTC timestamp `TS` appears to have been stamped per deploy and reused across artifacts — note
`20260625T063658Z` shows up as *both* an env backup and a `-prev-` container, and
`20260625T065252Z` as *both* a release directory and a `-prev-` container.

```
TS=$(date -u +%Y%m%dT%H%M%SZ)
SHA=<short commit sha>

# 1. Stage the release: export the repo tree at that commit
#    (mechanism unknown — no .git on the box, so scp/rsync/git archive from elsewhere)
/opt/qtw/releases/$TS-$SHA/

# 2. Build the image ON the droplet, context = REPO ROOT (not backend/)
docker build -t qtw-backend:$SHA -f backend/Dockerfile .

# 3. Back up the env if it changed
cp -p /opt/qtw/backend.env /opt/qtw/backend.env.bak-$TS

# 4. Retire the running container by RENAME (keeps it as instant rollback)
docker stop qtw-backend && docker rename qtw-backend qtw-backend-prev-$TS

# 5. Start the new one
docker run -d --name qtw-backend --restart unless-stopped \
  -p 127.0.0.1:8000:8000 --env-file /opt/qtw/backend.env qtw-backend:$SHA

# 6. Health check
curl -fsS http://127.0.0.1:8000/healthz
```

Step 2's context **must** be the repo root: `backend/Dockerfile` does
`COPY backend/pyproject.toml`, `COPY backend/src`, `COPY backend/README.md`, and sets
`PYTHONPATH=/app/backend/src`. Building from inside `backend/` fails.

Rollback was `docker stop qtw-backend && docker rm qtw-backend && docker rename
qtw-backend-prev-$TS qtw-backend && docker start qtw-backend`, plus restoring the matching
`backend.env.bak-$TS` if env had changed. This is the path used successfully on 2026-07-27 when
removing `DWAVE_API_TOKEN`, so it is verified, not merely inferred.

---

## Why `deploy/backend-deploy.sh` does not describe this

The script is a genuine, working pull-and-restart deploy — but for a different world:

| Script does | Reality |
|---|---|
| `docker pull "$IMAGE"` (line 64) | **Cannot work.** Tags were local and unnamespaced (`qtw-backend:48f080a`), and the box had no `/root/.docker`. A pull would fail or silently resolve nothing. |
| `docker stop` then `docker rm` (lines 22-27) | The box **renamed** to `qtw-backend-prev-$TS` and kept the container. |
| nothing about `releases/` | The box staged `releases/$TS-$SHA/` on every deploy. |
| nothing about building | The image was built on the droplet. |
| rollback re-runs `$OLD_IMAGE` | Correct in spirit, and the image tags for rollback did exist locally. |

Everything the script *does* say about the run invocation, the env-file path, the loopback bind, and
the 30 × 2s health poll matches reality exactly. It is the surrounding lifecycle that was missing.

## Why `docs/DEPLOY.md` does not describe this either

`docs/DEPLOY.md` documents a **CI-driven SSH deploy** — a manual GitLab `backend:deploy` job using
`DEPLOY_HOST`, `DEPLOY_SSH_PRIVATE_KEY`, `DEPLOY_USER`, `DEPLOY_SSH_PORT`. **That job was deleted in
commit `14395ea`** ("ci: drop unused SSH-based backend:deploy job"). Its "Deploy", "GitLab CI/CD
Variables", and "Applying Env Changes" sections therefore instruct steps that cannot be performed,
and "Remaining Deployment Work" still reads as though the droplet were unprovisioned.

Those `DEPLOY_*` CI variables and the `qtw-ci-deploy` key are consequently **standing credentials
with no consumer** — tracked for removal in QUI-877.

---

## Lessons worth keeping

1. **A deploy script in the repo is not evidence of how deploys happen.** Here the committed script
   was internally sound and simply unused, while the real procedure lived only in someone's terminal.
   The artifacts on disk (`releases/`, `-prev-` containers, tag names) were the only honest record.
2. **Tag an image with a commit sha and you have created an obligation to keep that commit
   reachable.** `48f080a` was built from a `deployment-dev` commit that was never merged, and that
   branch was later deleted server-side — leaving a production image tagged with an unfetchable sha.
   It was only recoverable because the release tree happened to still be on the box.
3. **Add `LABEL org.opencontainers.image.revision`.** Null labels meant the image could not attest to
   its own provenance, so proving what was deployed required hashing trees against a live container.
4. **Keep the env file somewhere other than the box.** `/opt/qtw/backend.env` was the single copy of
   `DATABASE_URL`, `DWAVE_API_TOKEN`, `RESEND_API_KEY`, `ADMIN_API_KEY`, and `KIOSK_SIGNUP_KEY`.
   Destroying the droplet without copying it off would have been unrecoverable.

---

## What replaced it

Flux Orbit, single instance, building from the `deploy/orbit` branch of this repo. Full record in
QUI-875. The essentials:

- Orbit clones the branch and builds on each node — **no registry image is involved**
- `PROJECT_PATH=backend`, `APP_PORT=8000`
- `RUN_COMMAND=/opt/flux-tools/conda/bin/uvicorn backend.api.app:app --host 0.0.0.0 --port 8000 --workers 1`
- `backend/requirements.txt` pins the dependency set, because Orbit re-resolves on every rebuild
- Secrets live in Orbit's encrypted env, not in a file on a host
- ⚠ **Any env-var change requires a Hard Redeploy, not a restart** — the Python environment is
  ephemeral per container while the packaged release persists, so a plain redeploy returns the app
  with no dependencies and it crash-loops on exit 127
