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
