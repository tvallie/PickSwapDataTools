import json
import pytest
from pathlib import Path
from fetch_draft_picks.historian import append_current_history, append_future_history


def test_append_current_creates_file(tmp_path):
    path = tmp_path / "current_pick_history.json"
    changes = [
        {"overall": 13, "round": 1, "pick_in_round": 13,
         "_json_abbr": "ATL", "proposed": {"abbr": "LAR", "team": "Los Angeles Rams"}}
    ]
    append_current_history(changes, "2026-04-16", path)
    data = json.loads(path.read_text())
    assert data["history"] == [
        {"overall": 13, "round": 1, "pick_in_round": 13,
         "date": "2026-04-16", "from": "ATL", "to": "LAR"}
    ]


def test_append_current_accumulates(tmp_path):
    path = tmp_path / "current_pick_history.json"
    changes = [{"overall": 1, "round": 1, "pick_in_round": 1,
                "_json_abbr": "LV", "proposed": {"abbr": "NYJ", "team": "New York Jets"}}]
    append_current_history(changes, "2026-04-15", path)
    append_current_history(changes, "2026-04-16", path)
    data = json.loads(path.read_text())
    assert len(data["history"]) == 2


def test_append_future_add(tmp_path):
    path = tmp_path / "future_pick_history.json"
    changes = [
        {"action": "add", "year": 2027, "round": 1, "original_abbr": "GB",
         "current_abbr": "DAL"}
    ]
    append_future_history(changes, "2026-04-16", path)
    data = json.loads(path.read_text())
    assert data["history"] == [
        {"year": 2027, "round": 1, "original_abbr": "GB",
         "date": "2026-04-16", "from": "GB", "to": "DAL"}
    ]


def test_append_future_update(tmp_path):
    path = tmp_path / "future_pick_history.json"
    changes = [
        {"action": "update", "year": 2027, "round": 2, "original_abbr": "BUF",
         "current_abbr": {"current": "CHI", "proposed": "KC"}}
    ]
    append_future_history(changes, "2026-04-16", path)
    data = json.loads(path.read_text())
    assert data["history"] == [
        {"year": 2027, "round": 2, "original_abbr": "BUF",
         "date": "2026-04-16", "from": "CHI", "to": "KC"}
    ]


def test_append_future_remove(tmp_path):
    path = tmp_path / "future_pick_history.json"
    changes = [
        {"action": "remove", "year": 2027, "round": 3, "original_abbr": "LAR",
         "current_abbr": "KC"}
    ]
    append_future_history(changes, "2026-04-16", path)
    data = json.loads(path.read_text())
    assert data["history"] == [
        {"year": 2027, "round": 3, "original_abbr": "LAR",
         "date": "2026-04-16", "from": "KC", "to": "LAR"}
    ]


def test_append_future_skips_unknown_action(tmp_path):
    path = tmp_path / "future_pick_history.json"
    changes = [{"action": "noop", "year": 2027, "round": 1, "original_abbr": "KC"}]
    append_future_history(changes, "2026-04-16", path)
    data = json.loads(path.read_text())
    assert data["history"] == []
