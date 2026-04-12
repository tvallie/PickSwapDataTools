import pytest
from unittest.mock import patch, MagicMock


def test_worker_emits_scrape_complete(qtbot):
    from gui.worker import ScraperWorker

    fake_picks = [
        {"overall": 1, "round": 1, "pick_in_round": 1,
         "team": "Las Vegas Raiders", "abbr": "LV",
         "is_comp": False, "original_team": "Las Vegas Raiders"},
    ]
    fake_results = [
        {"source": "tankathon", "picks": fake_picks, "method": "python",
         "elapsed": 1.0, "error": None},
        {"source": "espn", "picks": fake_picks, "method": "claude-haiku",
         "elapsed": 2.0, "error": None},
    ]
    existing_json = '{"picks": [{"overall": 1, "round": 1, "pick_in_round": 1, "team": "Las Vegas Raiders", "abbr": "LV", "is_comp": false, "original_team": "Las Vegas Raiders"}]}'

    mock_file = MagicMock()
    mock_file.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=existing_json)))
    mock_file.__exit__ = MagicMock(return_value=False)

    import json
    with patch("gui.worker.scrape_source", side_effect=fake_results), \
         patch("gui.worker.scrape_with_claude_fallback", side_effect=fake_results), \
         patch("gui.worker.CURRENT_SOURCES", [MagicMock(name="tankathon", priority=0), MagicMock(name="espn", priority=1)]), \
         patch("builtins.open", return_value=mock_file), \
         patch("json.load", return_value={"picks": fake_picks}):
        worker = ScraperWorker(mode="current", dry_run=True)
        with qtbot.waitSignal(worker.scrape_complete, timeout=5000) as blocker:
            worker.start()

    changes, ai = blocker.args
    assert isinstance(changes, list)
    assert isinstance(ai, dict)


def test_worker_emits_source_updated(qtbot):
    from gui.worker import ScraperWorker

    fake_picks = [{"overall": 1, "round": 1, "pick_in_round": 1,
                   "team": "Las Vegas Raiders", "abbr": "LV",
                   "is_comp": False, "original_team": "Las Vegas Raiders"}]
    results_iter = iter([
        {"source": "tankathon", "picks": fake_picks, "method": "python", "elapsed": 1.0, "error": None},
        {"source": "espn", "picks": fake_picks, "method": "python", "elapsed": 1.5, "error": None},
    ])
    signals_received = []

    with patch("gui.worker.scrape_source", side_effect=results_iter), \
         patch("gui.worker.CURRENT_SOURCES", [MagicMock(name="tankathon", priority=0), MagicMock(name="espn", priority=1)]), \
         patch("builtins.open", MagicMock()), \
         patch("json.load", return_value={"picks": fake_picks}):
        worker = ScraperWorker(mode="current", dry_run=True)
        worker.source_updated.connect(
            lambda name, method, elapsed, status: signals_received.append(name)
        )
        with qtbot.waitSignal(worker.scrape_complete, timeout=5000):
            worker.start()

    assert len(signals_received) >= 1
