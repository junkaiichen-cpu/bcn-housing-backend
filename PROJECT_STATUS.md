# BCN Housing backend prototype

## Status

Implemented backend demo flow:

1. A customer submits a BUY or RENT requirement with at least one contact method.
2. The requirement and a NEW lead are stored in SQLite.
3. Available property records are matched by deterministic, explainable rules.
4. A customer can request a viewing for a matching available property.
5. An authenticated administrator can review the lead, requirement, matches, notes, and history.
6. An administrator can create agents, assign an agent, and update lead status.
7. An administrator can manage viewing-request status, partner assignment, and report references.

Property records created for demonstration are explicitly labeled `DEMO`. No real listings or agency partnerships are included.

Existing valuation, regional comparison, geography, and rental-risk endpoints remain registered by the existing backend. The existing valuation helper tests and new API tests are run together in CI.

## Setup

Python 3.12 is the CI-tested runtime. Install dependencies in a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Configure administrator credentials and a unique signing secret through environment variables. Do not commit these values:

```bash
export APP_ENV=demo
export DATABASE_URL=sqlite:///./bcn_housing.db
export CORS_ALLOW_ORIGINS=http://localhost:3000
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD='replace-with-a-long-unique-password'
export ADMIN_TOKEN_SECRET="$(openssl rand -hex 32)"
```

`ADMIN_TOKEN_SECRET` must be at least 32 characters and the administrator password must be at least 12 characters. The application refuses administrator login when credentials are missing/weak or the signing secret is too short. Login attempts are limited to 10 per client IP per minute within one application process. Set `APP_ENV=production` in production to prevent automatic demo-property seeding. `CORS_ALLOW_ORIGINS` is a comma-separated allowlist; configure the actual frontend origin rather than using a wildcard. The default database is `./bcn_housing.db`; its schema is initialized on application startup using SQLAlchemy and SQLite `user_version` schema version 1. The local SQLite database file is restricted to owner read/write permissions on startup. This lightweight initializer creates missing tables; it is not a general-purpose column migration system.

Run the backend:

```bash
.venv/bin/uvicorn main:app --reload
```

Interactive API documentation is available at `/docs`.

## API endpoints

### Public

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/requirements` | Submit a BUY/RENT requirement; returns requirement and lead IDs without returning contact details. |
| `GET` | `/api/requirements/{requirement_id}/matches` | Return matching and excluded available properties, scores, explanations, incompatibilities, and missing information. |
| `GET` | `/api/properties` | List available properties; optional `transaction_type=BUY` or `RENT`. |
| `GET` | `/api/properties/{property_id}` | Retrieve an available property. |
| `POST` | `/api/viewing-requests` | Request a viewing for an available property that matches the requirement. |
| `POST` | `/api/admin/login` | Exchange configured admin credentials for an eight-hour bearer token. |

### Administrator — bearer token required

Send `Authorization: Bearer <access_token>` for every endpoint below.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/admin/properties` | Create a property; `data_label` is `DEMO` or `REAL`. |
| `GET` | `/api/admin/properties` | List all properties, including unavailable records. |
| `PATCH` | `/api/admin/properties/{property_id}/status` | Change property availability status. |
| `POST` | `/api/admin/agents` | Create an agency or independent agent profile. |
| `GET` | `/api/admin/agents` | List agent profiles and contact details. |
| `PATCH` | `/api/admin/agents/{agent_id}/status` | Activate/deactivate an agent and update verification status. |
| `GET` | `/api/admin/leads` | List leads and their private customer requirements; optional `status_filter`. |
| `GET` | `/api/admin/leads/{lead_id}` | View a lead, private requirement/contact details, matches, notes, and history. |
| `GET` | `/api/admin/leads/{lead_id}/matches` | Review suggested matching properties. |
| `PUT` | `/api/admin/leads/{lead_id}/agent` | Assign an active agent. |
| `PATCH` | `/api/admin/leads/{lead_id}/status` | Set a lead status. |
| `POST` | `/api/admin/leads/{lead_id}/notes` | Add an internal note. |
| `DELETE` | `/api/admin/leads/{lead_id}` | Delete the lead and its associated customer requirement, notes, history, and viewing requests. |
| `GET` | `/api/admin/viewing-requests` | List viewing requests, including private customer contact details. |
| `PATCH` | `/api/admin/viewing-requests/{request_id}` | Update viewing status, agent, preferred date, and report references. |

Lead statuses: `NEW`, `REVIEWING`, `MATCHED`, `CONTACTED`, `VIEWING_SCHEDULED`, `CONVERTED`, `CLOSED`.

Viewing statuses: `NEW`, `SCHEDULED`, `COMPLETED`, `CANCELLED`.

Matching weights can be configured with `MATCH_WEIGHT_BUDGET`, `MATCH_WEIGHT_LOCATION`, `MATCH_WEIGHT_PROPERTY_TYPE`, `MATCH_WEIGHT_BEDROOMS`, and `MATCH_WEIGHT_AREA` (defaults: 35, 25, 15, 15, and 10). Scores describe fit against the available, specified criteria; they are not guarantees. Free-text requirements are flagged for manual review and are not interpreted as AI.

## Example customer flow

Submit a requirement:

```bash
curl -X POST http://localhost:8000/api/requirements \
  -H 'Content-Type: application/json' \
  -d '{
    "transaction_type": "RENT",
    "budget_min": 900,
    "budget_max": 1600,
    "preferred_locations": ["Barcelona", "Eixample"],
    "property_type": "apartment",
    "bedrooms_min": 1,
    "area_min_sqm": 45,
    "timeline": "Within 2 months",
    "preferred_language": "zh",
    "contact_name": "Demo Customer",
    "contact_email": "customer@example.test"
  }'
```

The response contains `id` and `lead_id`. Use `id` to check matches:

```bash
curl http://localhost:8000/api/requirements/REQUIREMENT_ID/matches
```

Request a viewing with a matching property's `property_id`:

```bash
curl -X POST http://localhost:8000/api/viewing-requests \
  -H 'Content-Type: application/json' \
  -d '{
    "requirement_id": "REQUIREMENT_ID",
    "property_id": "PROPERTY_ID",
    "preferred_at": "2027-01-15T10:00:00+01:00",
    "customer_notes": "Weekend preferred"
  }'
```

## Example administrator flow

Login and retain the returned token:

```bash
curl -X POST http://localhost:8000/api/admin/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"replace-with-a-long-unique-password"}'
```

Use the token with the lead and agent endpoints, for example:

```bash
curl http://localhost:8000/api/admin/leads \
  -H 'Authorization: Bearer ACCESS_TOKEN'

curl -X PATCH http://localhost:8000/api/admin/leads/LEAD_ID/status \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"status":"REVIEWING"}'
```

## Remaining work and limitations

- Replace the existing startup-time fetch/execute of the pinned legacy backend source; current legacy API startup still requires network access.
- Use a managed production database and a real migration tool before schema evolution or multi-instance deployment.
- Configure HTTPS, deployment-level request rate limits, secret rotation, backups, retention policy, and operational monitoring before production use.
- Review legal-risk analysis and third-party contract-text processing, including customer consent and data handling.
- Validate regional data provenance and valuation assumptions; the current prototype is not a guarantee or legal advice.
- Add deployment-specific administrator provisioning/rotation and integration testing against the production runtime.
- The viewing process coordinates manually. Image/report references are metadata only; this backend does not upload files or provide video infrastructure.

## Live frontend integration check — 2026-11-09

The integration checks used the supplied deployed origins:

- Frontend: `https://bcn-housing-checker.vercel.app`
- Backend: `https://bcn-housing-backend.onrender.com`
- Frontend source inspected: public `junkaiichen-cpu/bcn-housing-checker` repository `main` branch.

### A. Confirmed with the real deployed backend

- `GET /api/properties` returned HTTP 200 with `{"properties":[]}`. The production property list is empty; no demo or real property records were returned.
- `GET /api/geography/tree` returned HTTP 200 with the expected `status`/`data` envelope and 12 comarca entries.
- `GET /openapi.json` returned HTTP 200 and listed the backend routes.
- An empty `POST /api/requirements` returned HTTP 422 with the expected validation error shape. This checks validation only; no successful production customer submission was made.
- `GET /api/admin/leads` without a token returned HTTP 401. `POST /api/admin/login` with an empty body returned HTTP 422. No credentials were guessed or attempted; successful admin login remains unverified.
- The Vercel site returned HTTP 200, and its compiled client bundle contained the configured fallback backend hostname `bcn-housing-backend.onrender.com`.
- Browser-origin CORS was **not working at check time**: the Vercel origin's preflight to `/api/requirements` and `/api/admin/login` returned HTTP 400 `Disallowed CORS origin`; the browser-origin property GET had no `Access-Control-Allow-Origin` response header.
- A targeted backend code change now includes the known Vercel origin in the default CORS allowlist. This does not change an explicit Render `CORS_ALLOW_ORIGINS` override and cannot repair the already-running deployment until redeployed. Set Render's `CORS_ALLOW_ORIGINS` to include `https://bcn-housing-checker.vercel.app` (and any Vercel preview origins that need access), then redeploy and repeat preflight checks.

### B. Confirmed against frontend source / local checks only

- The public frontend repository's `lib/api.ts` reads `NEXT_PUBLIC_BACKEND_URL`, with a fallback to the supplied Render backend. The live client bundle includes that backend hostname. The Vercel dashboard's configured environment-variable value itself was not accessible, so it is not independently confirmed. `NEXT_PUBLIC_API_BASE_URL` is not the variable used by this frontend source.
- The inspected frontend `main` branch calls `GET /api/geography/tree`, `POST /api/evaluate`, `POST /api/compare-regions`, and `POST /api/check-rental-risk`. Those request fields align with the inspected backend source; LLM-dependent success responses were not exercised against production.
- The inspected frontend source contains no calls to the property listing, customer requirement, matching, viewing, or admin APIs. Those flow endpoints are therefore not integrated by the inspected branch even if they may have been exercised against a mock backend elsewhere.
- In a temporary clone of the supplied frontend repository, `npx tsc --noEmit` passed and `npm run build` passed. `npm run lint` failed with 6 errors and 2 warnings in `app/page.tsx` (including explicit `any` and a React set-state-in-effect diagnostic). No frontend source was modified here.

### B. Confirmed with mock backend only (user-reported)

- The user reports that customer/admin frontend workflows passed against a temporary mock backend. The mock, test code, and test output were not present in the supplied repository or workspace, so this result could not be independently reproduced. It does not confirm compatibility with the deployed backend.

### C. Not tested / remaining blockers

- A successful customer requirement POST and full persistence/matching/viewing flow were not tested on production because that would create synthetic customer data. The supplied “staging backend URL” was a GitHub repository URL, not a deployed staging service. Repeat the write-flow tests on a staging deployment or with real, authorized customer data.
- The production property database is empty. Demo properties are supported only by starting the backend with `APP_ENV=demo`; the seeder inserts three records explicitly labeled `DEMO` only when the property table is empty. Do not enable this on production unless demo records are intentionally wanted there. A separate demo/staging database is recommended.
- Successful administrator authentication and all protected admin actions were not tested; no admin credentials were provided. Provide and use authorized credentials through a secure channel in an approved test environment.
- Live responses from valuation, regional comparison, and rental-risk endpoints were not exercised. Frontend/backend request compatibility was checked against source only; the comparison and rental-risk success paths may invoke Groq.
- The Vercel project settings and Render environment configuration are not accessible from this workspace. Set `NEXT_PUBLIC_BACKEND_URL` in the Vercel environment to the backend origin (without `/api`) for each deployed environment, and verify the configured value in Vercel. The checked-in frontend has a fallback, but explicit environment configuration is preferable.
- The deployed CORS policy must be updated in Render and redeployed before browser integration can be considered confirmed.
- The frontend test run used the public repository's `main` branch. Confirm that it is the same commit as the Vercel deployment; the deployed site build revision was not available from this workspace.
- The frontend install reported 14 npm audit findings (8 moderate, 5 high, 1 critical); these were not investigated or fixed in this backend-only integration check.

Do not treat the product as production-ready on the basis of these checks.
