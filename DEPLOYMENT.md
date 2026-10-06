# Docker and Delivery

This packages Analyq for a **private hosted preview**. It does not create a cloud
account, buy a server, publish your repository or deploy anything by itself.
The existing `docker-compose.yml` and development database are unchanged.

## What Runs Where

```text
Browser -> HTTPS gateway (hosting only) -> web:8080
                                          | /api/*
                                          v
                                        api:8000 -> db:5432
                                          |
                                          +-> Alpaca / Alpha Vantage / Gemini
```

- An **image** is the packaged application. A **container** runs that image.
- `backend/Dockerfile` installs locked Python dependencies and runs FastAPI as a
  non-root user. No development reload and one worker: existing caches, login
  throttling and expensive model work are process-local.
- `frontend/Dockerfile` compiles React, then serves the build using non-root Nginx.
  The final image does not contain Node, source files or `node_modules`.
- `frontend/nginx.conf` sends `/api/...` to FastAPI, stripping `/api`. This is a
  reverse proxy. The browser sees one website origin, including its login cookies.
  Requests may run up to ten minutes; upstream/provider limits still apply.
- `compose.deploy.yml` starts a private database, a one-off migration job, the API
  and the website. The database must be healthy and migrations must finish first.
- A Docker **volume** stores PostgreSQL data independently of container replacement.
  This deployment has a NEW volume and database, not your existing development data.
- `compose.https.yml` and `deploy/Caddyfile` add HTTPS and an extra password gate for
  hosting. Certificates are stored in their own persistent volume.

## First Local Container Run

Run commands from the repository root with Docker running.

1. Create the separate deployment configuration:

   ```sh
   cp .env.deploy.example .env.deploy
   chmod 600 .env.deploy
   ```

2. Generate two different secrets, running this twice:

   ```sh
   python3 -c 'import secrets; print(secrets.token_hex(32))'
   ```

   Put one in `POSTGRES_PASSWORD` and the other in `AUTH_SESSION_SECRET`.
   Use hex for the database password: it avoids URL escaping in the connection URL.
   Add your existing provider keys and Google client ID to `.env.deploy`.
   Do not copy the old `DATABASE_URL`: Compose supplies the correct internal address.
   Keep `AUTH_COOKIE_SECURE=false` for this loopback-only HTTP test.

3. Build and start:

   ```sh
   docker compose --env-file .env.deploy -f compose.deploy.yml up --build -d --wait
   ```

4. Open http://localhost:8080 and create a username/password account. For Google,
   add `http://localhost:8080` to the OAuth client's authorized JavaScript origins.
   Existing development accounts/chats are not in this new database. A deliberate
   backup/restore is needed to transfer them later.

5. Inspect or stop without deleting data:

   ```sh
   docker compose --env-file .env.deploy -f compose.deploy.yml ps
   docker compose --env-file .env.deploy -f compose.deploy.yml logs --tail=100 api migrate
   docker compose --env-file .env.deploy -f compose.deploy.yml down
   ```

**Do not add `--volumes` to a real deployment's down command. It deletes its data.**
Changing `POSTGRES_PASSWORD` after database initialization does not rotate the
stored database password. Plan that change using PostgreSQL, then update configuration.

`.dockerignore` allowlists exclude `.env`, local environments and generated artifacts.
Only the public `/api` address is embedded into the frontend; no provider keys are
build arguments. Do not paste the output of `docker compose config` or container
environment inspection publicly: these can expand secrets. Use `config --quiet`.

## Verify Without Spending Provider Credits

```sh
docker build --target test -t analyq-api:test backend
python3 scripts/container_smoke.py --backend-tests
```

This builds the production frontend (including lint/type checks), boots an isolated
stack on port 18080, runs fresh migrations, checks guest rejection, registers a test
user, saves a chat, replaces the database/API containers, checks persistence and
logs out. It also runs
the full Python suite including PostgreSQL integration tests. No provider keys are
supplied. Its randomly named test database/volume is removed afterwards. Use
`--port 18081` if 18080 is occupied. It is an HTTP integration test, not a browser
visual test or live Google/market-data test.

## What GitHub Automates

`.github/workflows/delivery.yml` defines:

1. Every push/PR: build the test image, run the container checks and backend tests.
2. Successful default-branch runs: publish the **exact tested images**, transferred
   between jobs as an artifact, to GitHub Container Registry (GHCR).
3. Manual Run workflow with `deploy=true`: test/publish, then deploy that commit to
   your configured Linux VM through SSH. Other branches cannot deploy.

Image names are `ghcr.io/OWNER/REPOSITORY-api:COMMIT_SHA` and
`ghcr.io/OWNER/REPOSITORY-web:COMMIT_SHA`, with owner/repository lowercased.
The workflow uses the repository's actual default branch; it does not assume main.
GitHub-hosted Ubuntu builds are Linux AMD64, so select an x86-64 host for this workflow.
Local Apple Silicon builds work locally but should not be uploaded to an x86 host
as a substitute. ARM hosting needs a corresponding runner or multi-platform build.

There is currently no configured GitHub remote. You must create/connect your own
repository before Actions can run. No school/private account is chosen for you.
After the first successful run, make the `verify` job a required branch-protection
check. Adding a workflow alone does NOT block merging failed code.

## Host Setup: Linux VM Path

This is an optional prepared path, not a hosting purchase recommendation. A managed
platform can use the Dockerfiles too, but needs its own networking/release setup:
the current Nginx `api` hostname specifically assumes this Compose network.

Before enabling the deployment job:

1. Choose a Linux x86-64 VM with Docker Engine and Compose v2. Give it sufficient
   memory for scikit-learn and PostgreSQL; measure peak use rather than assuming a
   tiny instance is enough. Use a dedicated deployment user. Docker group access
   is effectively root access and must be treated accordingly.
2. Point your domain's DNS at the VM. Open ports 80/443; restrict SSH appropriately.
   Do not expose PostgreSQL 5432, FastAPI 8000 or the loopback website 8080.
3. Create `~/analyq/.env.deploy` on the VM, mode 600. Fill provider keys and fresh
   database/session secrets, `HTTPS_DOMAIN=your.actual.domain`, and
   `AUTH_COOKIE_SECURE=true`. Keep `WEB_BIND=127.0.0.1`.
4. Set `PREVIEW_USER` and generate an independent private-preview password hash:

   ```sh
   docker run --rm -it caddy:2-alpine caddy hash-password
   ```

   Put the returned hash in single quotes in `PREVIEW_PASSWORD_HASH` to preserve
   its dollar signs. Keep the original password in your password manager. This
   browser password prompt protects the entire preview BEFORE app signup/login.
5. Add `https://your.actual.domain` to Google OAuth's authorized JavaScript origins.
6. On the VM, log Docker into GHCR if the images are private, using a credential
   with only the needed package-read permission. Do not put this token in the repo.
   Configure GHCR package access for your repository if publication is denied.
7. Create a GitHub Environment named `production`, restrict it to the default
   branch and enable required approval if your GitHub plan supports it.
8. Add Environment secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` and
   `DEPLOY_KNOWN_HOSTS`. The last is the server's verified SSH host-key entry;
   verify its fingerprint with your hosting console rather than blindly trusting
   a network scan. Use a dedicated deployment key, not your everyday personal key.

Choose **Actions -> Test, build and deliver -> Run workflow -> deploy=true** on the
default branch. The workflow transfers only deployment config/scripts; your `.env`
and provider credentials remain on the server. No secret API keys are needed in CI.

The deployment script pulls commit-tagged images, makes a pre-migration database
dump, runs migrations once, replaces services and checks the internal API. Failed
migrations stop the deployment. This simple deployment can have brief downtime;
it is not blue/green or zero-downtime. Check your public HTTPS URL after deployment:
internal health does not establish public DNS/certificate reachability.

## Recovery and Remaining Work

- The last successful release SHA is recorded in `~/analyq/.last-deployed-sha`.
  To restore an earlier compatible application release, run the deployment script
  with its old commit SHA. Images must still exist in GHCR.
- Database migrations are NOT automatically rolled back. An old image may be
  incompatible with a newer schema. Restore a tested backup or write a forward
  repair; never assume changing an image reverses database changes.
- Pre-release dumps go in `~/analyq/backups/` with private file permissions.
  Add scheduled encrypted off-host backups, retention and restore drills before
  depending on this database. A volume or on-server backup cannot survive VM loss.
- Keep the preview gate until per-account usage limits, signup controls and
  shared rate limiting exist. App login is not a quota. The existing login limiter
  sees the internal proxy IP and is intentionally conservative for a private app.
- Add cost monitoring, exception tracking and provider data-redistribution review
  before a public launch. Containerization alone does not complete production readiness.
- Update pinned base-image digests/actions and locked dependencies regularly through
  tested PRs. Python locks were seeded from installed development versions, resolved
  for Python 3.12 and hash-pinned. To intentionally refresh with `uv`:

  ```sh
  uv pip compile backend/pyproject.toml --python-version 3.12 --universal --generate-hashes --output-file backend/requirements.lock
  uv pip compile backend/pyproject.toml --extra dev --python-version 3.12 --universal --generate-hashes --constraint backend/requirements.lock --output-file backend/requirements-dev.lock
  ```

## References

- [Docker startup health and migration ordering](https://docs.docker.com/compose/how-tos/startup-order/)
- [GitHub image publishing](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
- [Caddy automatic HTTPS prerequisites](https://caddyserver.com/docs/automatic-https)
- [Caddy hashed-password access gate](https://caddyserver.com/docs/caddyfile/directives/basic_auth)

Suggested commit: `feat: containerize Analyq and add tested delivery workflow`
