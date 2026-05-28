import random

from app.core.config import settings


def maybe_fail():
    """
    Simulate random failure at the configured rate.
    Used to demonstrate retry + resume capabilities.
    """
    if random.random() < settings.FAILURE_RATE:
        raise RuntimeError("Simulated random stage failure (POC demo)")
