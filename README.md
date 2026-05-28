# AR Reconciliation Workflow Engine

Rule-based workflow engine for Accounts Receivable reconciliation with retry, resume, and background execution.

## Architecture

```
CSV / JSON Submission
        │
   FastAPI API
        │
  Idempotency Check
        │
   SQLite / PostgreSQL
    (workflow state)
        │
  BackgroundTasks
        │
┌───────┼────────┬───────────────┐
│       │        │               │
Ingest  Match  Validate     Route
│       │        │               │
└───────┼────────┴───────────────┘
        │
  Persist stage result
        │
  Retry on failure (up to 3×)
        │
  Resume from last stage
```

## Key Features

- **Background Processing**: FastAPI `BackgroundTasks` processes each workflow pipeline asynchronously
- **Retry Mechanism**: Configurable random failure simulation (20% default) with automatic retry (3 attempts)
- **Resume from Checkpoint**: Failed workflows resume from the last successful stage
- **Idempotency**: Duplicate submissions return the existing workflow ID
- **Bulk Upload**: CSV upload processes each row as an independent workflow in parallel
- **Persistent State**: SQLite (default) or PostgreSQL stores workflow state, stage results, and records
- **Modular Stages**: Ingestion → Matching → Validation → Decision Routing
- **Dashboard & Export**: Stats endpoint, enhanced workflow listing with staleness detection, CSV export

## Stack

| Component | Technology |
|-----------|-----------|
| API | FastAPI |
| Background Processing | FastAPI BackgroundTasks |
| Database | SQLite (default) / PostgreSQL |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Schema Validation | Pydantic v2 |
| Settings | pydantic-settings (`.env` support) |
| Logging | Structlog |
| Build | Hatchling |

## Quick Start

```bash
# Install dependencies
uv pip install -e .

# Run API (auto-creates SQLite DB on startup)
uvicorn app.api.routes:app --reload --port 8000

# Or use main.py
python main.py
```

Services:
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs

### PostgreSQL (optional)

Set environment variables or create a `.env` file:

```env
DB_TYPE=postgresql
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=secret
POSTGRES_DB=ar_reconciliation
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_TYPE` | `sqlite` | Database backend (`sqlite` or `postgresql`) |
| `DATABASE_URL` | `sqlite:///./data/ar_reconciliation.db` | SQLite connection string |
| `FAILURE_RATE` | `0.20` | Simulated random failure probability per stage |
| `MAX_RETRIES` | `3` | Max retry attempts per stage |
| `MATCH_TOLERANCE_PERCENT` | `5.0` | % difference allowed to count as MATCHED |
| `HIGH_VALUE_THRESHOLD` | `10000.0` | Invoice amount above which records are flagged high-value |
| `STALE_MINUTES` | `10` | Failed workflows older than this are marked stale |

## API Endpoints

### Submissions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/submit` | Submit single AR record (idempotent) |
| PUT | `/submit/{customer_id}` | Update existing record and reprocess |
| POST | `/bulk-upload` | Upload CSV for bulk processing |

### Workflows

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/workflow/{id}` | Get workflow status + all stage details |
| POST | `/resume/{id}` | Resume failed workflow from last checkpoint |
| GET | `/workflows` | List all workflows (filterable by status, paginated) |

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/stats` | Aggregate counts by status + routing decisions |
| GET | `/workflows/enhanced` | Workflow list with staleness flag and last error |
| GET | `/export` | Download completed results as CSV |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |

## Workflow Stages

1. **Ingestion**: Parse record, generate SHA-256 idempotency key, persist to DB
2. **Matching**: Compare invoice vs payment totals (with tolerance) → `MATCHED` / `PARTIAL` / `OVERPAID` / `OUTSTANDING`
3. **Validation**: Business rule checks — positive amounts, valid exchange rates, required fields
4. **Decision Routing**: Route based on match result + validation outcome → `AUTO_APPROVED` / `MANUAL_REVIEW` / `FINANCE_REVIEW` / `COLLECTION_QUEUE` / `REJECTED`

### Routing Logic

| Condition | Decision |
|-----------|----------|
| Validation failed | `REJECTED` |
| High-value + not matched | `FINANCE_REVIEW` |
| Matched | `AUTO_APPROVED` |
| Partial payment | `MANUAL_REVIEW` |
| Overpaid | `FINANCE_REVIEW` |
| Outstanding | `COLLECTION_QUEUE` |

## Database Schema

- `workflow_runs` — Tracks each workflow's current state, stage, and retry count
- `workflow_stage_state` — Records each stage execution attempt, output JSON, and errors
- `ar_records` — Persisted AR records from ingestion
- `processed_records` — SHA-256 idempotency key tracking

## Project Structure

```
app/
├── api/
│   ├── routes.py          # FastAPI app, lifespan, middleware, routers
│   ├── submissions.py     # POST /submit, PUT /submit/{id}, POST /bulk-upload
│   ├── workflows.py       # GET /workflow/{id}, POST /resume/{id}, GET /workflows
│   ├── dashboard.py       # GET /stats, /workflows/enhanced, /export
│   └── health.py          # GET /health
├── core/
│   ├── config.py          # Settings via pydantic-settings
│   └── database.py        # SQLAlchemy engine, session, Base
├── models/
│   ├── record.py          # ARRecord, ProcessedRecord ORM models
│   └── workflow.py        # WorkflowRun, WorkflowStageState ORM models
├── schemas/
│   └── workflow.py        # Pydantic request/response schemas
└── services/
    ├── pipeline.py        # Stage orchestrator with retry loop
    ├── ingest.py          # Ingestion stage logic
    ├── matching.py        # Matching stage logic
    ├── validation.py      # Validation stage logic
    ├── routing.py         # Decision routing stage logic
    ├── failure_sim.py     # Random failure simulator (POC demo)
    └── workflow_engine.py # Workflow CRUD and state transitions
```

## Example Usage

```bash
# Submit single record
curl -X POST http://localhost:8000/submit \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "CUST-0001",
    "customer_name": "Customer 0001",
    "invoice_total": 3892.38,
    "payment_total": 3316.88
  }'

# Upload CSV
curl -X POST http://localhost:8000/bulk-upload \
  -F "file=@data/erp_export.csv"

# Check workflow status
curl http://localhost:8000/workflow/{workflow_id}

# Resume failed workflow
curl -X POST http://localhost:8000/resume/{workflow_id}
```

## Project Structure

```
ar_reconciliation/
├── app/
│   ├── api/
│   │   └── routes.py           # FastAPI endpoints
│   ├── core/
│   │   ├── celery_app.py       # Celery configuration
│   │   ├── config.py           # App settings (Pydantic)
│   │   └── database.py         # SQLAlchemy engine + session
│   ├── models/
│   │   ├── workflow.py         # WorkflowRun, WorkflowStageState
│   │   └── record.py          # ARRecord, ProcessedRecord
│   ├── schemas/
│   │   └── workflow.py         # Pydantic request/response models
│   ├── services/
│   │   ├── failure_sim.py      # Random failure simulation
│   │   ├── ingest.py           # Ingestion stage
│   │   ├── matching.py         # Matching stage
│   │   ├── validation.py       # Validation stage
│   │   ├── routing.py          # Decision routing stage
│   │   └── workflow_engine.py  # Workflow state management
│   └── workers/
│       └── tasks.py            # Celery task definitions
├── alembic/                    # Database migrations
├── data/
│   └── erp_export.csv          # Kaggle dataset
├── pyproject.toml
├── main.py
└── README.md
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./data/ar_reconciliation.db` | Database connection |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery results |
| `FAILURE_RATE` | `0.20` | Simulated failure rate |
| `MAX_RETRIES` | `3` | Max retry attempts per stage |
| `RETRY_COUNTDOWN` | `5` | Seconds between retries |
