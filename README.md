# Homework - FastAPI + Postgres + Grafana

Small CI/CD pipeline run collector with FastAPI, PostgreSQL, and a pre-provisioned Grafana dashboard.

## What’s inside
- API: FastAPI (Python 3.12) with endpoints for ingesting and reading pipeline runs.
- DB: PostgreSQL 16 with `pipeline_runs` table and TIMESTAMPTZ columns.
- Grafana: Provisioned Postgres datasource and dashboard (counts, durations, latest runs).
- Docker Compose to run everything locally.

## Prerequisites
- Docker + Docker Compose
- Fill in a real env file based on `.env.example`

## Quickstart
1) Copy env template and edit secrets:
   ```sh
   cp .env.example .env
   # set strong values for POSTGRES_PASSWORD, GRAFANA_ADMIN_PASSWORD, etc.
   ```
2) Start the stack:
   ```sh
   docker compose up --build
   # Watch out for proxy!
   ```
3) Services:
   - API: http://localhost:8000 (OpenAPI docs at `/docs`)
   - Grafana: http://localhost:3000 (login `admin` / `GRAFANA_ADMIN_PASSWORD`)
   - Postgres host inside Compose: `db` (not exposed on host)

## API
- **POST `/events`**  
  Accepts a single object or array of objects. Upserts on `(build_id, branch)`. Example:
  ```json
  [
    {
      "build_id": "build-1001",
      "branch": "main",
      "result": "success",
      "start_time": "2025-09-28T10:15:00Z",
      "end_time": "2025-09-28T10:18:42Z"
    },
    {
      "build_id": "build-1004",
      "branch": "hotfix/payment-timeout",
      "result": "running",
      "start_time": "2025-09-29T07:55:00Z"
    }
  ]
  ```
- **GET `/events`**  
  Returns latest 100 runs ordered by `start_time` desc (includes computed `duration_seconds`).

- **GET `/stats/summary`**  
  Counts by result, average duration by branch, and latest run per branch.

- **GET `/health`**  
  Simple DB ping for container/orchestrator health checks.

### Sample curl
Ingest a single run:
```sh
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{"build_id":"build-1001","branch":"main","result":"success","start_time":"2025-09-28T10:15:00Z","end_time":"2025-09-28T10:18:42Z"}'
```

Ingest multiple runs:
```sh
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '[{"build_id":"build-1002","branch":"feature/login-refactor","result":"failed","start_time":"2025-09-28T11:02:10Z","end_time":"2025-09-28T11:04:10Z"},{"build_id":"build-1003","branch":"main","result":"canceled","start_time":"2025-09-28T12:30:00Z","end_time":"2025-09-28T12:31:00Z"}]'
```

List recent runs:
```sh
curl http://localhost:8000/events
```

Summary:
```sh
curl http://localhost:8000/stats/summary
```

Validation rules:
- Required: `build_id`, `branch`, `result`, `start_time`
- `result` ∈ {success, failed, canceled, running}
- `end_time` (if present) must be >= `start_time`
- Upsert key: `(build_id, branch)`
- Idempotency: hash of build_id, branch, start/end, result, repo_name, commit_sha, runner, workflow; unique constraint on `idempotency_key`.

Labels supported on runs: `repo_name`, `commit_sha`, `runner`, `workflow`.

## Database
Table `pipeline_runs`:
- `id` SERIAL PK
- `build_id` TEXT NOT NULL
- `branch` TEXT NOT NULL
- `result` TEXT CHECK in (success, failed, canceled, running)
- `start_time` TIMESTAMPTZ NOT NULL
- `end_time` TIMESTAMPTZ NULL
- `idempotency_key` TEXT NOT NULL UNIQUE
- `repo_name`, `commit_sha`, `runner`, `workflow` (optional labels)
- UNIQUE (build_id, branch)
- CHECK (end_time IS NULL OR end_time >= start_time)

## Grafana
- Datasource: Postgres (host `db`, db `${POSTGRES_DB}`, user `${POSTGRES_USER}`)
- Dashboard: `Pipeline Runs` auto-loaded (counts all-time/24h, avg duration by branch, latest 20 runs)
- Variables: `branch`, `repo` to filter panels; queries respect these filters.
- Default time range: now-24h → now (widen if your data is outside that window)
- If provisioning ever looks stale, restart Grafana with a clean volume:
  ```sh
  docker compose down -v grafana
  docker compose up -d grafana
  ```
