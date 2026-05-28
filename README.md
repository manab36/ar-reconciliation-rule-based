# AR Reconciliation Workflow Engine

Asynchronous workflow engine for Accounts Receivable reconciliation with retry, resume, and parallel execution.

## Architecture

```
CSV/Kaggle Dataset
       │
  FastAPI API
       │
 Idempotency Check
       │
     SQLite
 (workflow state)
       │
  Celery Queue
  (Redis Broker)
       │
┌──────┼──────┬──────────────┐
│      │      │              │
Ingest Match Validate    Route
│      │      │              │
└──────┼──────┴──────────────┘
       │
 Persist stage result
     (SQLite)
       │
  Retry on failure
       │
 Resume from last stage
```

## Key Features

- **Async Processing**: Celery workers process each workflow stage in parallel
- **Retry Mechanism**: Random failures (20% rate) with automatic retry (3 attempts)
- **Resume from Checkpoint**: Failed workflows resume from last successful stage
- **Idempotency**: Duplicate submissions return existing workflow ID
- **Parallel Execution**: Multiple workflows processed concurrently via Celery workers
- **Persistent State**: SQLite stores workflow state, stage results, and records
- **Modular Stages**: Ingestion → Matching → Validation → Decision Routing

## Stack

| Component | Technology |
|-----------|-----------|
| API | FastAPI |
| Async Workers | Celery |
| Broker | Redis |
| Database | SQLite (POC) |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Schema Validation | Pydantic |
| Logging | Structlog |

## Quick Start

```bash
# Install dependencies
uv pip install -e .

# Start Redis (required for Celery broker)
redis-server

# Run API
uvicorn app.api.routes:app --reload --port 8000

# Run Celery worker (separate terminal)
celery -A app.workers.tasks worker --loglevel=info
```

Services:
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/submit` | Submit single AR record |
| POST | `/bulk-upload` | Upload CSV for bulk processing |
| GET | `/workflow/{id}` | Get workflow status + stage details |
| POST | `/resume/{id}` | Resume failed workflow |
| GET | `/workflows` | List all workflows (filterable) |
| GET | `/health` | Health check |

## Workflow Stages

1. **Ingestion**: Parse record, generate idempotency key, persist to DB
2. **Matching**: Compare invoice vs payment totals → MATCHED/PARTIAL/OVERPAID/OUTSTANDING
3. **Validation**: Business rule checks (positive amounts, valid rates, required fields)
4. **Decision Routing**: Route to AUTO_APPROVED/MANUAL_REVIEW/FINANCE_REVIEW/COLLECTION_QUEUE/REJECTED

## Database Schema

- `workflow_runs` — Tracks each workflow's current state and stage
- `workflow_stage_state` — Records each stage execution attempt and output
- `ar_records` — Persisted AR records from ingestion
- `processed_records` — Idempotency tracking

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
