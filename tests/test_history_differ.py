import pytest
from fetch_draft_picks.differ import diff_current_history, diff_future_history


EXISTING_CURRENT = [
    {"overall": 13, "round": 1, "pick_in_round": 13, "date": "2026-01-15", "from": "ATL", "to": "LAR"},
]

EXISTING_FUTURE = [
    {"year": 2027, "round": 1, "original_abbr": "GB", "date": "2026-01-15", "from": "GB", "to": "DAL"},
]


def test_diff_current_returns_new_entries():
    scraped = [
        {"overall": 13, "round": 1, "pick_in_round": 13, "date": "2026-01-15", "from": "ATL", "to": "LAR"},  # dup
        {"overall": 14, "round": 1, "pick_in_round": 14, "date": "2026-02-01", "from": "SF", "to": "NYG"},   # new
    ]
    result = diff_current_history(scraped, EXISTING_CURRENT)
    assert len(result) == 1
    assert result[0]["overall"] == 14


def test_diff_current_all_new():
    scraped = [
        {"overall": 5, "round": 1, "pick_in_round": 5, "date": "2026-03-01", "from": "NE", "to": "MIA"},
    ]
    result = diff_current_history(scraped, EXISTING_CURRENT)
    assert len(result) == 1


def test_diff_current_all_existing():
    result = diff_current_history(EXISTING_CURRENT, EXISTING_CURRENT)
    assert result == []


def test_diff_current_empty_scraped():
    result = diff_current_history([], EXISTING_CURRENT)
    assert result == []


def test_diff_current_empty_existing():
    scraped = [{"overall": 1, "round": 1, "pick_in_round": 1, "date": "2026-01-01", "from": "NE", "to": "BUF"}]
    result = diff_current_history(scraped, [])
    assert len(result) == 1


def test_diff_future_returns_new_entries():
    scraped = [
        {"year": 2027, "round": 1, "original_abbr": "GB", "date": "2026-01-15", "from": "GB", "to": "DAL"},   # dup
        {"year": 2027, "round": 2, "original_abbr": "BUF", "date": "2026-02-01", "from": "BUF", "to": "KC"}, # new
    ]
    result = diff_future_history(scraped, EXISTING_FUTURE)
    assert len(result) == 1
    assert result[0]["original_abbr"] == "BUF"


def test_diff_future_all_existing():
    result = diff_future_history(EXISTING_FUTURE, EXISTING_FUTURE)
    assert result == []


def test_diff_future_empty_scraped():
    result = diff_future_history([], EXISTING_FUTURE)
    assert result == []
