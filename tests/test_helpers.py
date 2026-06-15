from app.utils.helpers import (
    calculate_progress,
    calculate_speed,
    chunk_list,
    estimate_time_remaining,
)


def test_calculate_progress_basic():
    assert calculate_progress(50, 100) == 50
    assert calculate_progress(0, 100) == 0
    assert calculate_progress(100, 100) == 100


def test_calculate_progress_exceeds_total():
    assert calculate_progress(110, 100) == 100


def test_calculate_progress_zero_total():
    assert calculate_progress(10, 0) == 0


def test_calculate_speed():
    assert calculate_speed(1000, 2.0) == 500
    assert calculate_speed(0, 5.0) == 0
    assert calculate_speed(1000, 0) == 0


def test_estimate_time_remaining():
    # 500 rows done in 1s → 500 rows/s → 500 remaining → 1s
    assert estimate_time_remaining(500, 1000, 1.0) == 1
    assert estimate_time_remaining(0, 1000, 1.0) == 0


def test_chunk_list():
    result = chunk_list([1, 2, 3, 4, 5], 2)
    assert result == [[1, 2], [3, 4], [5]]


def test_chunk_list_empty():
    assert chunk_list([], 10) == []
