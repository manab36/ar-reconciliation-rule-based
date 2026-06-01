from app.core.config import settings
from database_ops.models import WorkflowStageName

MAX_RETRIES = settings.MAX_RETRIES

AR_RECONCILIATION_PIPELINE_STAGES = {
    WorkflowStageName.INGESTION: {
        "handler": "app.services.ar_reconciliation_pipeline.stage_ingestion.execute",
        "retryable": True,
        "max_retries": MAX_RETRIES or 5,
    },
    WorkflowStageName.NORMALIZATION: {
        "handler": "app.services.ar_reconciliation_pipeline.stage_normalization.execute",
        "retryable": True,
        "max_retries": MAX_RETRIES or 5,
    },
    WorkflowStageName.BALANCE_COMPUTE: {
        "handler": "app.services.ar_reconciliation_pipeline.stage_balance_compute.execute",
        "retryable": True,
        "max_retries": MAX_RETRIES or 5,
    },
    WorkflowStageName.RECONCILIATION: {
        "handler": "app.services.ar_reconciliation_pipeline.stage_reconciliation.execute",
        "retryable": True,
        "max_retries": MAX_RETRIES or 5,
    },
    WorkflowStageName.VALIDATION_RULES: {
        "handler": "app.services.ar_reconciliation_pipeline.stage_validate_rules.execute",
        "retryable": True,
        "max_retries": MAX_RETRIES or 5,
    },
    WorkflowStageName.VERDICT_GENERATION: {
        "handler": "app.services.ar_reconciliation_pipeline.stage_verdict_generation.execute",
        "retryable": False,
        "max_retries": MAX_RETRIES or 5,
    },
    WorkflowStageName.REPORTING: {
        "handler": "app.services.ar_reconciliation_pipeline.stage_reporting.execute",
        "retryable": True,
        "max_retries": MAX_RETRIES or 5,
    },
}
