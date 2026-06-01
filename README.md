# AR Reconciliation Workflow Engine

A production-ready, asynchronous Accounts Receivable reconciliation workflow engine built with Python. Demonstrates advanced workflow orchestration patterns including state persistence, automatic retries, checkpoint-based resume, parallel execution, and idempotent request handling.

## 🎯 Problem Statement

Build an asynchronous AR reconciliation workflow engine that:
- Processes records through modular stages: ingestion, matching, validation, and decision routing
- Handles random failures with automatic retry logic
- Resumes from the last successful stage rather than restarting from scratch
- Supports parallel execution with persistent workflow state
- Safely handles duplicate or repeated submissions

**Note:** This is a workflow orchestration POC, not an ML accuracy assignment.

## 🏗️ Architecture

```mermaid
flowchart TD
    A[CSV / JSON Submission] --> B[FastAPI API]
    B --> C{Idempotency Check}
    C -->|Duplicate| Z[Return existing workflow ID]
    C -->|New| D[Create WorkflowRun - PENDING]
    D --> E[BackgroundTasks: Run Pipeline]
    E --> S1[Stage 1: Ingestion]
    S1 --> S2[Stage 2: Normalization]
    S2 --> S3[Stage 3: Balance Compute]
    S3 --> S4[Stage 4: Reconciliation]
    S4 --> S5[Stage 5: Validation Rules]
    S5 --> S6[Stage 6: Verdict Generation]
    S6 --> S7[Stage 7: Reporting]
    S7 --> G[COMPLETED]
    S1 -->|Fails max retries| F[FAILED]
    S2 -->|Fails max retries| F
    S3 -->|Fails max retries| F
    S4 -->|Fails max retries| F
    S5 -->|Fails max retries| F
    S7 -->|Fails max retries| F
    F --> R[POST /resume/{id} - retry from checkpoint]
    R --> E
```

## 📋 Pipeline Stages

| Stage | Purpose | Output |
|-------|---------|--------|
| **1. Ingestion** | Accept and validate input data | `transactions` |
| **2. Normalization** | Clean data, convert types, validate exchange rates | `normalized_transactions` |
| **3. Balance Compute** | Calculate outstanding/unapplied amounts | `customer_balance_snapshot` |
| **4. Reconciliation** | Calculate expected balance and differences | `reconciliation_result` |
| **5. Validation Rules** | Apply business rules (MATCH, OVERPAID, etc.) | `validation_result` |
| **6. Verdict Generation** | Generate final verdict with confidence score | `reconciliation_verdict` |
| **7. Reporting** | Generate summary, exception, and audit reports | `final_reports` |

### Business Rules

| Rule | Condition | Result |
|------|-----------|--------|
| A | `abs(difference) < 0.01` | MATCH |
| B | `customer_balance < expected_balance` | OVERPAID |
| C | `payment_unapplied > 0` | UNAPPLIED_PAYMENT |
| D | `credit_available > 0` | UNAPPLIED_CREDIT |
| E | `customer_balance > expected_balance` | UNDERPAID |

## ⚙️ Key Features

### 1. **Asynchronous Background Processing**
- FastAPI `BackgroundTasks` processes each workflow pipeline asynchronously
- Non-blocking API responses - submit and get workflow ID immediately

### 2. **Configurable Retry Mechanism**
- Random failure simulation (configurable, default 20%) for testing
- Automatic retry up to `MAX_RETRIES` (default 5) per stage
- Exponential backoff ready (extensible)

### 3. **Checkpoint-Based Resume**
- Each stage persists its output to `workflow_stage_state` table
- Failed workflows can resume from the exact failed stage
- Previous stage outputs are loaded from database on resume

### 4. **Idempotent Request Handling**
- Duplicate submissions (same `customer_id`) return existing workflow
- Database constraints prevent race conditions
- `IntegrityError` gracefully handled

### 5. **Bulk Processing**
- CSV upload processes multiple records in parallel
- Each row becomes an independent workflow
- Progress tracking with error reporting

### 6. **Persistent State Management**
- SQLite (default) or PostgreSQL backend
- Atomic commits ensure data integrity
- Full audit trail via `workflow_stage_state`

## 🛠️ Tech Stack

| Component | Technology |
|-----------|-----------|
| API Framework | FastAPI |
| Background Processing | FastAPI BackgroundTasks |
| Database | SQLite (default) / PostgreSQL |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Schema Validation | Pydantic v2 |
| Configuration | pydantic-settings (`.env` support) |
| Logging | Structlog (JSON/Console) |
| Build System | Hatchling / uv |

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Installation

```bash
# Clone and navigate
cd ar-reconciliation-rule-based

# Install dependencies with uv
uv sync

# Or with pip
pip install -e .

# Run database migrations
uv run alembic upgrade head

# Start the server
uv run python main.py
```

### Services
- **API:** http://localhost:8000
- **Swagger Docs:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### PostgreSQL Setup (Optional)

Create a `.env` file:

```env
DB_TYPE=postgresql
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=ar_reconciliation

# Pipeline configuration
FAILURE_RATE=0.20
MAX_RETRIES=5
```

## 📡 API Endpoints

### Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Basic health check |
| GET | `/health/liveness` | Kubernetes liveness probe |
| GET | `/health/readiness` | Kubernetes readiness probe |
| GET | `/health/detailed` | Comprehensive health info |

### AR Records
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ar_records/submit` | Submit single AR record |
| POST | `/ar_records/bulk-upload` | Upload CSV for bulk processing |
| GET | `/ar_records/workflow/{id}` | Get workflow status & stages |
| GET | `/ar_records/workflows` | List all workflows (paginated) |
| GET | `/ar_records/workflows/enhanced` | List with staleness detection |
| POST | `/ar_records/resume/{id}` | Resume failed workflow |
| GET | `/ar_records/stats` | Dashboard statistics |
| GET | `/ar_records/export` | Export results as CSV |

## 📊 Data Model

### Input CSV Format

```csv
Customer ID,Customer Name,Customer Balance,Invoice Total,Invoice applied amount,Invoice exchange rate,Payment Total,Payment applied amount,Payment exchange rate,Credit Total,Credit applied amount,Credit exchange rate,Adjustment Total,Adjustment applied amount,Adjustment exchange rate
CUST-0001,Customer 0001,3486.58,3892.38,241.57,1.1371,3316.88,2375.22,0.8873,910.95,676.97,1.0237,1310.49,944.51,1.1211
```

### Database Schema

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────────┐
│    customers    │     │   workflow_runs     │     │ workflow_stage_state │
├─────────────────┤     ├─────────────────────┤     ├──────────────────────┤
│ id (PK)         │────▶│ customer_id (FK)    │────▶│ workflow_id (FK)     │
│ name            │     │ id (PK)             │     │ id (PK)              │
│ email           │     │ status              │     │ stage_name           │
│ address         │     │ current_stage       │     │ status               │
│ phone_number    │     │ retry_count         │     │ retry_count          │
└─────────────────┘     │ created_at          │     │ output_json          │
                        │ updated_at          │     │ error_message        │
        ▲               └─────────────────────┘     │ created_at           │
        │                                           │ updated_at           │
┌───────┴─────────┐                                 └──────────────────────┘
│   ar_records    │
├─────────────────┤
│ id (PK)         │
│ customer_id(FK) │
│ customer_balance│
│ invoice_*       │
│ payment_*       │
│ credit_*        │
│ adjustment_*    │
└─────────────────┘
```

## 🔄 Workflow States

| State | Description |
|-------|-------------|
| `PENDING` | Workflow created, not yet started |
| `RUNNING` | Pipeline actively processing |
| `RETRYING` | Stage failed, attempting retry |
| `FAILED` | Max retries exceeded, needs manual resume |
| `COMPLETED` | All stages completed successfully |

## 🔧 Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_TYPE` | `sqlite` | Database type (`sqlite` or `postgresql`) |
| `DATABASE_URL` | `sqlite:///./data/ar_reconciliation.db` | SQLite connection string |
| `FAILURE_RATE` | `0.20` | Random failure probability (0-1) |
| `MAX_RETRIES` | `5` | Maximum retry attempts per stage |
| `TIMEZONE` | `Asia/Kolkata` | Timezone for timestamps |

## 🧪 Testing

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=app --cov-report=html
```

## 🔐 Concurrency & Safety Guarantees

| Scenario | Handling |
|----------|----------|
| Stage exception | Retried up to `MAX_RETRIES` times with logging |
| All retries exhausted | Workflow marked `FAILED`, error persisted |
| Concurrent duplicate submit | DB constraint catches race; returns existing workflow |
| DB connection lost | Context manager rolls back, workflow marked `FAILED` |
| Resume after failure | Loads previous stage output, resumes from next stage |

## 📁 Project Structure

```
ar-reconciliation-rule-based/
├── main.py                          # FastAPI application entry point
├── pyproject.toml                   # Project configuration
├── alembic.ini                      # Alembic configuration
├── alembic/                         # Database migrations
├── app/
│   ├── core/
│   │   ├── config.py               # Settings with pydantic-settings
│   │   └── database.py             # SQLAlchemy setup
│   ├── routes/
│   │   ├── ar_reconciliation.py    # AR API endpoints
│   │   └── health.py               # Health check endpoints
│   ├── schemas/                     # Pydantic models
│   └── services/
│       └── ar_reconciliation_pipeline/
│           ├── pipeline_config.py   # Stage configuration
│           ├── pipeline_runner.py   # Pipeline orchestrator
│           ├── stage_ingestion.py
│           ├── stage_normalization.py
│           ├── stage_balance_compute.py
│           ├── stage_reconciliation.py
│           ├── stage_validate_rules.py
│           ├── stage_verdict_generation.py
│           └── stage_reporting.py
├── database_ops/
│   ├── models.py                    # SQLAlchemy models
│   ├── repositories/                # Data access layer
│   ├── services/                    # Business logic
│   └── validations/                 # Input validation
├── data/
│   └── erp_export.csv              # Sample dataset
└── tests/
    └── endpoints.ipynb             # Interactive API tests
```

## 📈 Extending the System

### Adding a New Pipeline Stage

1. Create `stage_newstage.py` in `app/services/ar_reconciliation_pipeline/`
2. Implement `execute(data: dict) -> dict` function
3. Add to `pipeline_config.py`:
   ```python
   WorkflowStageName.NEW_STAGE: {
       "handler": "app.services.ar_reconciliation_pipeline.stage_newstage.execute",
       "retryable": True,
       "max_retries": 5,
   }
   ```
4. Add enum value to `WorkflowStageName` in `models.py`
5. Run Alembic migration

### Customizing Business Rules

Edit `stage_validate_rules.py` to add/modify validation rules:
```python
def _apply_custom_rule(record: Dict[str, Any]) -> Dict[str, Any]:
    # Your custom logic here
    pass
```

## 📜 License

MIT License - See [LICENSE](LICENSE) file.

---

Built with ❤️ as a POC demonstrating production-grade workflow orchestration patterns.
