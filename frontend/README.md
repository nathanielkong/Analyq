# Analyq Frontend

React and TypeScript frontend for Analyq.

## Local Setup

From the `frontend` directory:

```bash
npm install
```

## Run The Frontend

```bash
npm run dev
```

The app expects the backend API to run at:

```text
http://localhost:8000
```

Override this with `VITE_API_BASE_URL`.

## Vercel + Render

In Vercel, select root directory `frontend`, preset Vite, build command
`npm run build`, and output directory `dist`.

Production builds default to `/api`. `vercel.json` forwards `/api/*` to
`https://analyq-api.onrender.com/*`, stripping the `/api` prefix. API responses
must not be cached by the CDN because they can contain private account data.
Keep `VITE_API_BASE_URL` unset or set to `/api` in Vercel, then redeploy; Vite
embeds this value at build time. Never use localhost or a direct Render URL
for this proxy setup. Never put database credentials or provider keys in Vite variables.

Set `BACKEND_CORS_ORIGINS=https://analyq.vercel.app` on Render: password login
explicitly checks the request origin even through a proxy. Keep
`REQUIRE_AUTH=true` and `AUTH_COOKIE_SECURE=true`. The API's host-only,
HttpOnly, SameSite=Lax cookie is then delivered through the frontend origin.
Add `https://analyq.vercel.app` to the Google OAuth client's authorized
JavaScript origins. Preview deployments need separately approved origins.

After deployment, verify `/api/health` returns JSON, `/api/auth/config` enables
the intended login methods, then test login, page reload, and logout. Guest
requests to protected routes should return 401, not 200. Render's free service
can take time to wake up; long AI requests also remain subject to host/proxy timeouts.

Run the focused API routing checks (no live providers or credentials required):

```bash
node --experimental-vm-modules --test tests/api-routing.test.cjs
```

## Build

```bash
npm run build
```
