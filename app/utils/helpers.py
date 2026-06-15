import math
import time
import uuid
from typing import Any


def new_uuid() -> str:
    return str(uuid.uuid4())


def estimate_time_remaining(
    processed_rows: int,
    total_rows: int,
    elapsed_seconds: float,
) -> int:
    """Return seconds remaining; 0 when complete or indeterminate."""
    if processed_rows <= 0 or total_rows <= 0 or elapsed_seconds <= 0:
        return 0
    rate = processed_rows / elapsed_seconds
    remaining_rows = max(0, total_rows - processed_rows)
    return math.ceil(remaining_rows / rate) if rate > 0 else 0


def calculate_speed(processed_rows: int, elapsed_seconds: float) -> int:
    """Return rows per second, rounded to nearest integer."""
    if elapsed_seconds <= 0:
        return 0
    return round(processed_rows / elapsed_seconds)


def calculate_progress(processed: int, total: int) -> int:
    """Return 0-100 integer percentage."""
    if total <= 0:
        return 0
    return min(100, round((processed / total) * 100))


def chunk_list(lst: list[Any], size: int) -> list[list[Any]]:
    """Split *lst* into sub-lists of at most *size* elements."""
    return [lst[i : i + size] for i in range(0, len(lst), size)]


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Timer:
    """Simple elapsed-time helper."""

    def __init__(self) -> None:
        self._start = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def reset(self) -> None:
        self._start = time.monotonic()
