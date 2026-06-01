"""
Failure Simulation Utilities

Shared utilities for simulating random failures in pipeline stages
to test retry logic.
"""

import random

from app.core.config import settings


class StageFailureError(Exception):
    """Simulated random failure for retry testing."""

    pass


def maybe_fail(stage_name: str) -> None:
    """
    Simulate random failure based on FAILURE_RATE setting.

    Args:
        stage_name: Name of the current stage (for error message)

    Raises:
        StageFailureError: Randomly raised based on FAILURE_RATE probability
    """
    if random.random() < settings.FAILURE_RATE:
        raise StageFailureError(f"Simulated random failure in {stage_name} stage")
