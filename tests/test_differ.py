"""Tests for fetch_draft_picks.differ."""
from fetch_draft_picks.differ import diff_current_picks, compare_current_to_existing


def _pick(overall, team, abbr, is_comp=False, original_team=None):
    return {
        "overall": overall, "round": 1, "pick_in_round": overall,
        "team": team, "abbr": abbr, "is_comp": is_comp,
        "original_team": original_team or team,
    }


def test_no_conflicts():
    picks = [_pick(1, "Las Vegas", "LV"), _pick(2, "NY Jets", "NYJ")]
    sources = {"tankathon": picks, "pfr": picks}
    conflicts = diff_current_picks(sources)
    assert conflicts == []


def test_one_conflict():
    source_a = [_pick(1, "Las Vegas", "LV"), _pick(2, "NY Jets", "NYJ")]
    source_b = [_pick(1, "Las Vegas", "LV"), _pick(2, "New England", "NE")]
    sources = {"tankathon": source_a, "pfr": source_b}
    conflicts = diff_current_picks(sources)
    assert len(conflicts) == 1
    assert conflicts[0]["overall"] == 2
    assert conflicts[0]["values"]["tankathon"]["abbr"] == "NYJ"
    assert conflicts[0]["values"]["pfr"]["abbr"] == "NE"


def test_compare_to_existing_no_change():
    picks = [_pick(1, "Las Vegas", "LV")]
    changes = compare_current_to_existing(picks, picks)
    assert changes == []


def test_compare_to_existing_detects_change():
    existing = [_pick(2, "NY Jets", "NYJ")]
    scraped = [_pick(2, "New England", "NE", original_team="NY Jets")]
    changes = compare_current_to_existing(scraped, existing)
    assert len(changes) == 1
    assert changes[0]["overall"] == 2
    assert changes[0]["current"]["abbr"] == "NYJ"
    assert changes[0]["proposed"]["abbr"] == "NE"
