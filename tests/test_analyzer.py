"""Tests for fetch_draft_picks.analyzer."""
from unittest.mock import MagicMock, patch
from fetch_draft_picks.analyzer import select_model, analyze_conflicts


def test_no_conflicts_returns_none():
    model, reason = select_model(conflicts=[], high_stake_rounds=set())
    assert model is None


def test_few_simple_conflicts_uses_haiku():
    conflicts = [{"overall": 5, "round": 1}]  # 1 conflict, round 1 but only one
    # Round 1 alone with ≤3 conflicts and no cross-source disagreement → Haiku
    model, reason = select_model(conflicts=conflicts, high_stake_rounds=set())
    assert model == "claude-haiku-4-5-20251001"


def test_many_conflicts_uses_sonnet():
    conflicts = [{"overall": i, "round": 2} for i in range(5)]
    model, reason = select_model(conflicts=conflicts, high_stake_rounds=set())
    assert model == "claude-sonnet-4-6"


def test_high_volume_uses_opus():
    conflicts = [{"overall": i, "round": 1} for i in range(12)]
    model, reason = select_model(conflicts=conflicts, high_stake_rounds={1})
    assert model == "claude-opus-4-6"


def test_high_stakes_round1_small_conflict_count_uses_sonnet():
    # Few conflicts but round 1/2 involved → at least Sonnet
    conflicts = [{"overall": 3, "round": 1}]
    model, reason = select_model(conflicts=conflicts, high_stake_rounds={1})
    assert model == "claude-sonnet-4-6"


def test_analyze_conflicts_calls_correct_model():
    conflicts = [{"overall": 5, "round": 2, "values": {"tankathon": {"abbr": "NE"}, "pfr": {"abbr": "IND"}}}]
    news_snippets = ["Patriots acquired pick from Colts on Apr 3."]
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"5": {"summary": "NE correct", "confidence": "high"}}')]

    with patch("fetch_draft_picks.analyzer.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = mock_response
        result = analyze_conflicts(conflicts, news_snippets, mode="current")

    assert "5" in result
    assert result["5"]["confidence"] == "high"
