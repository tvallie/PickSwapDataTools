# Draft Pick Scraper Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a modular Python CLI tool that scrapes NFL draft pick ownership from multiple sites, diffs them deterministically, uses Claude AI to analyze conflicts, and interactively asks for approval before writing changes to `json/draft_order_current.json` and `json/future_pick_trades.json`.

**Architecture:** Modular package `fetch_draft_picks/` with five focused modules — scraper, differ, analyzer, deployer, and the CLI orchestrator. Python scraping is attempted first per source; Claude Haiku HTML parsing is the fallback. AI analysis runs only when conflicts exist, using the cheapest model sufficient for the complexity.

**Tech Stack:** Python 3.9+ stdlib + `requests` + `beautifulsoup4` + `anthropic` SDK. `pytest` for tests.

---

## Task 1: Package Scaffold

**Files:**
- Create: `fetch_draft_picks/__init__.py`
- Create: `fetch_draft_picks/__main__.py`
- Create: `fetch_draft_picks/scraper.py`
- Create: `fetch_draft_picks/differ.py`
- Create: `fetch_draft_picks/analyzer.py`
- Create: `fetch_draft_picks/deployer.py`
- Create: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/test_differ.py`
- Create: `tests/test_analyzer.py`
- Create: `tests/test_deployer.py`

**Step 1: Install dependencies**

```bash
pip3 install requests beautifulsoup4 anthropic pytest
```

**Step 2: Create requirements.txt**

```
requests>=2.31
beautifulsoup4>=4.12
anthropic>=0.25
pytest>=8.0
```

**Step 3: Create all empty package files**

Each file gets only a module docstring for now:

`fetch_draft_picks/__init__.py`:
```python
"""fetch_draft_picks — NFL draft pick scraper and updater."""
```

`fetch_draft_picks/scraper.py`, `differ.py`, `analyzer.py`, `deployer.py`, `__main__.py`:
```python
"""[module name] — [one-line description]."""
```

`tests/__init__.py`: empty file.

**Step 4: Verify the package is importable**

```bash
python3 -c "import fetch_draft_picks; print('OK')"
```
Expected: `OK`

**Step 5: Commit**

```bash
git add fetch_draft_picks/ requirements.txt tests/
git commit -m "feat: scaffold fetch_draft_picks package"
```

---

## Task 2: differ.py — Normalize and Diff Current Picks

Deterministic comparison of current-year pick lists from multiple sources.

**Files:**
- Modify: `fetch_draft_picks/differ.py`
- Modify: `tests/test_differ.py`

**Data structures** the differ works with:

Each scraper returns a normalized list for current picks:
```python
[
    {
        "overall": 1, "round": 1, "pick_in_round": 1,
        "team": "Las Vegas", "abbr": "LV",
        "is_comp": False, "original_team": "Las Vegas"
    },
    ...
]
```

A conflict looks like:
```python
{
    "overall": 14, "round": 1, "pick_in_round": 14,
    "values": {
        "tankathon": {"team": "New England", "abbr": "NE"},
        "pfr":       {"team": "Indianapolis", "abbr": "IND"}
    }
}
```

**Step 1: Write the failing tests**

```python
# tests/test_differ.py
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
    scraped =  [_pick(2, "New England", "NE", original_team="NY Jets")]
    changes = compare_current_to_existing(scraped, existing)
    assert len(changes) == 1
    assert changes[0]["overall"] == 2
    assert changes[0]["current"]["abbr"] == "NYJ"
    assert changes[0]["proposed"]["abbr"] == "NE"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_differ.py -v
```
Expected: `ImportError` or `FAILED` — functions not yet implemented.

**Step 3: Implement differ.py**

```python
"""differ.py — deterministic diffing of pick lists across sources and vs existing JSON."""


def diff_current_picks(sources: dict[str, list[dict]]) -> list[dict]:
    """Compare current-year pick lists from multiple sources.

    Args:
        sources: {source_name: [pick, ...]}

    Returns:
        List of conflict dicts, one per overall pick slot where sources disagree.
    """
    if len(sources) < 2:
        return []

    source_names = list(sources.keys())
    # Index each source by overall pick number
    indexed = {
        name: {p["overall"]: p for p in picks}
        for name, picks in sources.items()
    }

    all_overalls = sorted(
        {overall for picks in indexed.values() for overall in picks}
    )

    conflicts = []
    for overall in all_overalls:
        values = {
            name: indexed[name][overall]
            for name in source_names
            if overall in indexed[name]
        }
        # Compare team + abbr across sources
        abbrs = {v["abbr"] for v in values.values()}
        if len(abbrs) > 1:
            conflicts.append({
                "overall": overall,
                "round": next(iter(values.values()))["round"],
                "pick_in_round": next(iter(values.values()))["pick_in_round"],
                "values": {name: {"team": v["team"], "abbr": v["abbr"]}
                           for name, v in values.items()},
            })
    return conflicts


def compare_current_to_existing(
    scraped: list[dict], existing: list[dict]
) -> list[dict]:
    """Diff scraped consensus picks against the existing JSON.

    Returns proposed changes — picks where scraped data differs from existing.
    """
    existing_idx = {p["overall"]: p for p in existing}
    changes = []
    for pick in scraped:
        overall = pick["overall"]
        ex = existing_idx.get(overall)
        if ex is None:
            # New pick slot (e.g. comp pick added)
            changes.append({"overall": overall, "current": None, "proposed": pick})
        elif pick["abbr"] != ex["abbr"] or pick.get("is_comp") != ex.get("is_comp"):
            changes.append({
                "overall": overall,
                "round": pick["round"],
                "pick_in_round": pick["pick_in_round"],
                "current": {"team": ex["team"], "abbr": ex["abbr"],
                            "is_comp": ex.get("is_comp", False),
                            "original_team": ex.get("original_team", ex["team"])},
                "proposed": {"team": pick["team"], "abbr": pick["abbr"],
                             "is_comp": pick.get("is_comp", False),
                             "original_team": pick.get("original_team", pick["team"])},
            })
    return changes
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_differ.py -v
```
Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add fetch_draft_picks/differ.py tests/test_differ.py
git commit -m "feat: implement current picks differ"
```

---

## Task 3: differ.py — Future Picks Diff

**Files:**
- Modify: `fetch_draft_picks/differ.py`
- Modify: `tests/test_differ.py`

Future pick normalized format per source:
```python
[{"year": 2027, "round": 1, "original_abbr": "IND", "current_abbr": "NYJ"}, ...]
```

**Step 1: Add failing tests**

```python
from fetch_draft_picks.differ import diff_future_picks, compare_future_to_existing

def _fp(year, round_, orig, curr):
    return {"year": year, "round": round_, "original_abbr": orig, "current_abbr": curr}

def test_future_no_conflicts():
    picks = [_fp(2027, 1, "IND", "NYJ")]
    sources = {"overthecap": picks, "tankathon": picks}
    assert diff_future_picks(sources) == []

def test_future_conflict():
    a = [_fp(2027, 1, "IND", "NYJ")]
    b = [_fp(2027, 1, "IND", "NE")]
    sources = {"overthecap": a, "tankathon": b}
    conflicts = diff_future_picks(sources)
    assert len(conflicts) == 1
    assert conflicts[0]["original_abbr"] == "IND"
    assert conflicts[0]["values"]["overthecap"] == "NYJ"
    assert conflicts[0]["values"]["tankathon"] == "NE"

def test_future_compare_to_existing_no_change():
    picks = [_fp(2027, 1, "IND", "NYJ")]
    assert compare_future_to_existing(picks, picks) == []

def test_future_compare_detects_new_pick():
    existing = [_fp(2027, 1, "IND", "NYJ")]
    scraped = [_fp(2027, 1, "IND", "NYJ"), _fp(2027, 2, "DAL", "NE")]
    changes = compare_future_to_existing(scraped, existing)
    assert len(changes) == 1
    assert changes[0]["action"] == "add"

def test_future_compare_detects_ownership_change():
    existing = [_fp(2027, 1, "IND", "NYJ")]
    scraped =  [_fp(2027, 1, "IND", "NE")]
    changes = compare_future_to_existing(scraped, existing)
    assert len(changes) == 1
    assert changes[0]["action"] == "update"
    assert changes[0]["current_abbr"]["current"] == "NYJ"
    assert changes[0]["current_abbr"]["proposed"] == "NE"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_differ.py::test_future_no_conflicts -v
```
Expected: `ImportError` — functions not yet defined.

**Step 3: Implement future picks differ (append to differ.py)**

```python
def _future_key(pick: dict) -> tuple:
    return (pick["year"], pick["round"], pick["original_abbr"])


def diff_future_picks(sources: dict[str, list[dict]]) -> list[dict]:
    """Compare future traded picks from multiple sources."""
    if len(sources) < 2:
        return []

    indexed = {
        name: {_future_key(p): p["current_abbr"] for p in picks}
        for name, picks in sources.items()
    }
    all_keys = {k for idx in indexed.values() for k in idx}

    conflicts = []
    for key in sorted(all_keys):
        values = {name: idx[key] for name, idx in indexed.items() if key in idx}
        if len(set(values.values())) > 1:
            year, round_, orig = key
            conflicts.append({
                "year": year, "round": round_, "original_abbr": orig,
                "values": values,
            })
    return conflicts


def compare_future_to_existing(
    scraped: list[dict], existing: list[dict]
) -> list[dict]:
    """Diff scraped future picks against existing JSON. Returns proposed changes."""
    existing_idx = {_future_key(p): p for p in existing}
    scraped_idx  = {_future_key(p): p for p in scraped}

    changes = []
    # Detect updates and additions
    for key, pick in scraped_idx.items():
        ex = existing_idx.get(key)
        if ex is None:
            changes.append({"action": "add", **pick})
        elif pick["current_abbr"] != ex["current_abbr"]:
            year, round_, orig = key
            changes.append({
                "action": "update",
                "year": year, "round": round_, "original_abbr": orig,
                "current_abbr": {"current": ex["current_abbr"],
                                 "proposed": pick["current_abbr"]},
            })
    # Detect removals
    for key, ex in existing_idx.items():
        if key not in scraped_idx:
            changes.append({"action": "remove", **ex})
    return changes
```

**Step 4: Run all differ tests**

```bash
pytest tests/test_differ.py -v
```
Expected: All 8 tests PASS.

**Step 5: Commit**

```bash
git add fetch_draft_picks/differ.py tests/test_differ.py
git commit -m "feat: implement future picks differ"
```

---

## Task 4: analyzer.py — Model Selection

Pure function — no API calls needed here, fully testable.

**Files:**
- Modify: `fetch_draft_picks/analyzer.py`
- Modify: `tests/test_analyzer.py`

**Step 1: Write failing tests**

```python
# tests/test_analyzer.py
from fetch_draft_picks.analyzer import select_model

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
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_analyzer.py -v
```
Expected: `ImportError`.

**Step 3: Implement select_model**

```python
"""analyzer.py — AI conflict analysis and model selection."""

HAIKU   = "claude-haiku-4-5-20251001"
SONNET  = "claude-sonnet-4-6"
OPUS    = "claude-opus-4-6"


def select_model(
    conflicts: list[dict],
    high_stake_rounds: set[int],
) -> tuple[str | None, str]:
    """Choose the cheapest Claude model sufficient for the conflict complexity.

    Returns:
        (model_id, reason_string) — model_id is None if no AI call needed.
    """
    n = len(conflicts)

    if n == 0:
        return None, "no conflicts — skipping AI analysis"

    has_high_stakes = bool(high_stake_rounds & {1, 2})

    if n >= 10 or (n >= 5 and has_high_stakes):
        return OPUS, f"{n} conflicts, high complexity"
    if n >= 4 or has_high_stakes:
        return SONNET, f"{n} conflicts" + (", includes R1/R2" if has_high_stakes else "")
    return HAIKU, f"{n} simple conflict(s)"
```

**Step 4: Run tests**

```bash
pytest tests/test_analyzer.py -v
```
Expected: All 5 tests PASS.

**Step 5: Commit**

```bash
git add fetch_draft_picks/analyzer.py tests/test_analyzer.py
git commit -m "feat: implement model selection logic"
```

---

## Task 5: analyzer.py — Claude API Integration

**Files:**
- Modify: `fetch_draft_picks/analyzer.py`
- Modify: `tests/test_analyzer.py`

**Step 1: Add failing test using a mock**

```python
from unittest.mock import MagicMock, patch
from fetch_draft_picks.analyzer import analyze_conflicts

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
```

**Step 2: Run to verify it fails**

```bash
pytest tests/test_analyzer.py::test_analyze_conflicts_calls_correct_model -v
```
Expected: `ImportError`.

**Step 3: Implement analyze_conflicts**

```python
import json
import anthropic

# Prompt is kept minimal to reduce tokens — only conflict data + relevant news
_CURRENT_PROMPT = """\
You are an NFL draft pick ownership expert. Below are pick ownership conflicts \
between data sources, followed by recent news snippets.

Conflicts (JSON):
{conflicts_json}

News snippets:
{news_text}

For each conflict, identify which source is most likely correct and why. \
Reply ONLY with a JSON object keyed by overall pick number (as string), \
each value having keys: "summary" (one sentence), "confidence" ("high"/"medium"/"low"), \
"recommended_abbr" (the team abbreviation you believe is correct).
"""

_FUTURE_PROMPT = """\
You are an NFL draft pick trade expert. Below are conflicts in future traded pick \
ownership between data sources, followed by recent news snippets.

Conflicts (JSON):
{conflicts_json}

News snippets:
{news_text}

For each conflict, identify which source is most likely correct and why. \
Reply ONLY with a JSON object keyed by "YEAR_ROUND_ORIGABBR" (e.g. "2027_1_IND"), \
each value having keys: "summary" (one sentence), "confidence" ("high"/"medium"/"low"), \
"recommended_current_abbr".
"""


def analyze_conflicts(
    conflicts: list[dict],
    news_snippets: list[str],
    mode: str,  # "current" or "future"
) -> dict:
    """Send conflicts to Claude and return per-conflict analysis.

    Args:
        conflicts: output of diff_current_picks or diff_future_picks
        news_snippets: recent headlines/snippets from news sources
        mode: "current" or "future"

    Returns:
        Dict keyed by pick identifier → {summary, confidence, recommended_*}
    """
    model, reason = select_model(
        conflicts=conflicts,
        high_stake_rounds={c.get("round", 99) for c in conflicts},
    )
    if model is None:
        return {}

    print(f"\n  AI model selected: {model} ({reason})")

    prompt_template = _CURRENT_PROMPT if mode == "current" else _FUTURE_PROMPT
    prompt = prompt_template.format(
        conflicts_json=json.dumps(conflicts, indent=2),
        news_text="\n".join(f"- {s}" for s in news_snippets) or "None available.",
    )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  Warning: AI response was not valid JSON. Raw:\n{raw}")
        return {}
```

**Step 4: Run tests**

```bash
pytest tests/test_analyzer.py -v
```
Expected: All tests PASS.

**Step 5: Commit**

```bash
git add fetch_draft_picks/analyzer.py tests/test_analyzer.py
git commit -m "feat: implement Claude conflict analysis"
```

---

## Task 6: deployer.py — Archiving

**Files:**
- Modify: `fetch_draft_picks/deployer.py`
- Modify: `tests/test_deployer.py`

**Step 1: Write failing tests**

```python
# tests/test_deployer.py
import json
import tempfile
from pathlib import Path
from fetch_draft_picks.deployer import archive_json

def test_archive_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "draft_order_current.json"
        archive_dir = Path(tmp) / "archive"
        src.write_text('{"test": 1}')
        archived = archive_json(src, archive_dir, date_str="2026-04-10")
        assert archived.exists()
        assert archived.name == "draft_order_current_2026-04-10.json"
        assert src.exists()  # original still present (copy, not move)

def test_archive_collision_appends_suffix():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "draft_order_current.json"
        archive_dir = Path(tmp) / "archive"
        src.write_text('{"test": 1}')
        first  = archive_json(src, archive_dir, date_str="2026-04-10")
        src.write_text('{"test": 2}')
        second = archive_json(src, archive_dir, date_str="2026-04-10")
        assert first.name  == "draft_order_current_2026-04-10.json"
        assert second.name == "draft_order_current_2026-04-10_2.json"
```

**Step 2: Run to verify they fail**

```bash
pytest tests/test_deployer.py -v
```
Expected: `ImportError`.

**Step 3: Implement archive_json**

```python
"""deployer.py — archive JSON files and SCP to Bluehost."""
import shutil
import subprocess
import os
from pathlib import Path


def archive_json(src: Path, archive_dir: Path, date_str: str) -> Path:
    """Copy src to archive_dir with date appended to stem. Returns archive path."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem  # e.g. "draft_order_current"
    candidate = archive_dir / f"{stem}_{date_str}.json"
    i = 2
    while candidate.exists():
        candidate = archive_dir / f"{stem}_{date_str}_{i}.json"
        i += 1
    shutil.copy2(src, candidate)
    return candidate
```

**Step 4: Run tests**

```bash
pytest tests/test_deployer.py -v
```
Expected: Both PASS.

**Step 5: Commit**

```bash
git add fetch_draft_picks/deployer.py tests/test_deployer.py
git commit -m "feat: implement JSON archiving"
```

---

## Task 7: deployer.py — SCP Upload

**Files:**
- Modify: `fetch_draft_picks/deployer.py`
- Modify: `tests/test_deployer.py`

**Step 1: Add failing test**

```python
from unittest.mock import patch, call
from fetch_draft_picks.deployer import upload_files

def test_upload_calls_scp_for_each_file():
    files = ["/tmp/draft_order_current.json", "/tmp/archive/draft_order_current_2026-04-10.json"]
    with patch("fetch_draft_picks.deployer.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        results = upload_files(files)
    assert mock_run.call_count == len(files)
    assert all(r["success"] for r in results)

def test_upload_reports_failure():
    with patch("fetch_draft_picks.deployer.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        results = upload_files(["/tmp/draft_order_current.json"])
    assert not results[0]["success"]
```

**Step 2: Run to verify they fail**

```bash
pytest tests/test_deployer.py::test_upload_calls_scp_for_each_file -v
```
Expected: `ImportError`.

**Step 3: Implement upload_files**

```python
SSH_HOST       = "67.20.76.241"
SSH_USER       = "vallieor"
REMOTE_JSON    = "public_html/website_3650ab54/json"
SSH_KEY        = os.path.expanduser("~/.ssh/id_ed25519")


def upload_files(local_paths: list[str]) -> list[dict]:
    """SCP each file to Bluehost. Returns list of {path, success, error}."""
    results = []
    env = os.environ.copy()
    env["SSH_AUTH_SOCK"] = ""  # prevent agent interference

    for path in local_paths:
        filename = os.path.basename(path)
        # Determine remote subdirectory (archive files go into json/archive/)
        if "archive" in path.replace("\\", "/"):
            remote = f"{SSH_USER}@{SSH_HOST}:{REMOTE_JSON}/archive/{filename}"
        else:
            remote = f"{SSH_USER}@{SSH_HOST}:{REMOTE_JSON}/{filename}"

        result = subprocess.run(
            ["scp", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", path, remote],
            check=False, env=env,
        )
        results.append({
            "path": path,
            "remote": remote,
            "success": result.returncode == 0,
            "error": None if result.returncode == 0 else f"exit code {result.returncode}",
        })
    return results
```

**Step 4: Run all deployer tests**

```bash
pytest tests/test_deployer.py -v
```
Expected: All PASS.

**Step 5: Commit**

```bash
git add fetch_draft_picks/deployer.py tests/test_deployer.py
git commit -m "feat: implement SCP upload"
```

---

## Task 8: scraper.py — Source Registry and Base Interface

This task defines the scraper contract and registry. Actual site-specific parsing is stubbed; Task 9 fills it in.

**Files:**
- Modify: `fetch_draft_picks/scraper.py`

**Step 1: Inspect each scraping site manually**

Before writing any parsing code, open each URL in a browser and inspect the HTML structure for the data you need. For each source note:
- The URL(s) to fetch
- The CSS selector or table structure containing pick/trade data
- Whether JavaScript rendering is required (if yes, Python scraping will likely fail → Claude fallback)

Sites to inspect:
- Current picks:
  - `https://www.espn.com/nfl/draft/rounds/_/season/2026`
  - `https://www.nfldraftbuzz.com/DraftOrder/2026`
  - `https://www.tankathon.com/nfl/full_draft`
  - `https://prosportstransactions.com/football/DraftTrades/Years/2026.htm`
  - `https://www.si.com/nfl/updated-2026-nfl-draft-order-full-list-of-picks-all-seven-rounds`
  - `https://www.nflmockdraftdatabase.com/draft-order/2026-nfl-draft-order`
  - `https://www.pro-football-reference.com/years/2026/draft.htm`
- Future picks:
  - `https://overthecap.com/draft`
  - `https://www.tankathon.com/picks/future_picks`
  - `https://www.nfltraderumors.co/future-draft-picks`
  - `https://football.realgm.com/analysis/3656/NFL-Future-Draft-Picks-By-Team`
- News: `https://profootballtalk.nbcsports.com`, `https://www.nfl.com/news`, `https://www.espn.com/nfl/`

Record findings before implementing Step 2.

**Step 2: Implement source registry and base scraper**

```python
"""scraper.py — Python scraping with Claude HTML fallback."""
import time
import logging
from dataclasses import dataclass, field
from typing import Callable

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("fetch_draft_picks.scraper")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


@dataclass
class Source:
    name: str
    url: str
    mode: str          # "current" or "future" or "news"
    parse_fn: Callable # fn(html: str) -> list[dict]
    priority: int = 0  # lower = tried first


# Registry — populated at bottom of file
CURRENT_SOURCES: list[Source] = []
FUTURE_SOURCES:  list[Source] = []
NEWS_SOURCES:    list[Source] = []


def fetch_html(url: str, timeout: int = 20) -> str:
    """Fetch raw HTML via requests. Raises on HTTP error."""
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def scrape_source(source: Source) -> dict:
    """Attempt Python scraping; return result dict with metadata."""
    t0 = time.time()
    try:
        html = fetch_html(source.url)
        picks = source.parse_fn(html)
        elapsed = round(time.time() - t0, 1)
        logger.info(
            "[scraper] %-30s OK  (python)   %.1fs",
            source.name, elapsed,
        )
        return {"source": source.name, "picks": picks, "method": "python",
                "elapsed": elapsed, "error": None}
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        logger.warning("[scraper] %-30s FAIL→fallback  error=%s", source.name, e)
        return {"source": source.name, "picks": None, "method": None,
                "elapsed": elapsed, "error": str(e)}
```

**Step 3: Add stub parse functions for each source**

Below the `Source` dataclass, add one stub per source. These will be replaced in Task 9 with real parsing once you've inspected the HTML.

```python
# ── Current pick parsers (stubs — replace with real selectors after site inspection) ──

def _parse_espn_current(html: str) -> list[dict]:
    raise NotImplementedError("ESPN current parser not yet implemented")

def _parse_nfldraftbuzz_current(html: str) -> list[dict]:
    raise NotImplementedError("NFLDraftBuzz current parser not yet implemented")

def _parse_tankathon_current(html: str) -> list[dict]:
    raise NotImplementedError("Tankathon current parser not yet implemented")

def _parse_prosportstrans_current(html: str) -> list[dict]:
    raise NotImplementedError("ProSportsTransactions current parser not yet implemented")

def _parse_si_current(html: str) -> list[dict]:
    raise NotImplementedError("SI current parser not yet implemented")

def _parse_nflmockdb_current(html: str) -> list[dict]:
    raise NotImplementedError("NFLMockDB current parser not yet implemented")

def _parse_pfr_current(html: str) -> list[dict]:
    raise NotImplementedError("PFR current parser not yet implemented")


# ── Future pick parsers (stubs) ──

def _parse_overthecap_future(html: str) -> list[dict]:
    raise NotImplementedError("OverTheCap future parser not yet implemented")

def _parse_tankathon_future(html: str) -> list[dict]:
    raise NotImplementedError("Tankathon future parser not yet implemented")

def _parse_nfltraderumors_future(html: str) -> list[dict]:
    raise NotImplementedError("NFLTradeRumors future parser not yet implemented")

def _parse_realgm_future(html: str) -> list[dict]:
    raise NotImplementedError("RealGM future parser not yet implemented")


# ── News fetch ──

def _fetch_news_snippets(urls: list[str], max_per_site: int = 5) -> list[str]:
    """Fetch recent headlines from news sites. Returns plaintext snippets."""
    snippets = []
    for url in urls:
        try:
            html = fetch_html(url)
            soup = BeautifulSoup(html, "html.parser")
            # Generic: grab all <h2> and <h3> tags as headline proxies
            for tag in soup.find_all(["h2", "h3"])[:max_per_site]:
                text = tag.get_text(strip=True)
                if text:
                    snippets.append(f"[{url}] {text}")
        except Exception as e:
            logger.warning("[news] Failed to fetch %s: %s", url, e)
    return snippets


# ── Source registry ──

CURRENT_SOURCES = [
    Source("espn",              "https://www.espn.com/nfl/draft/rounds/_/season/2026",                                                    "current", _parse_espn_current,          priority=0),
    Source("nfldraftbuzz",      "https://www.nfldraftbuzz.com/DraftOrder/2026",                                                           "current", _parse_nfldraftbuzz_current,   priority=1),
    Source("tankathon",         "https://www.tankathon.com/nfl/full_draft",                                                               "current", _parse_tankathon_current,      priority=2),
    Source("prosportstrans",    "https://prosportstransactions.com/football/DraftTrades/Years/2026.htm",                                   "current", _parse_prosportstrans_current, priority=3),
    Source("si",                "https://www.si.com/nfl/updated-2026-nfl-draft-order-full-list-of-picks-all-seven-rounds",                "current", _parse_si_current,             priority=4),
    Source("nflmockdraftdb",    "https://www.nflmockdraftdatabase.com/draft-order/2026-nfl-draft-order",                                  "current", _parse_nflmockdb_current,      priority=5),
    Source("pro-football-ref",  "https://www.pro-football-reference.com/years/2026/draft.htm",                                            "current", _parse_pfr_current,            priority=6),
]

FUTURE_SOURCES = [
    Source("overthecap",        "https://overthecap.com/draft",                                        "future", _parse_overthecap_future,    priority=0),
    Source("tankathon-future",  "https://www.tankathon.com/picks/future_picks",                        "future", _parse_tankathon_future,     priority=1),
    Source("nfltraderumors",    "https://www.nfltraderumors.co/future-draft-picks",                    "future", _parse_nfltraderumors_future, priority=2),
    Source("realgm",            "https://football.realgm.com/analysis/3656/NFL-Future-Draft-Picks-By-Team", "future", _parse_realgm_future,   priority=3),
]

NEWS_URLS = [
    "https://profootballtalk.nbcsports.com",
    "https://www.nfl.com/news",
    "https://www.espn.com/nfl/",
]
```

**Step 4: Verify import works**

```bash
python3 -c "from fetch_draft_picks.scraper import CURRENT_SOURCES; print(len(CURRENT_SOURCES), 'current sources registered')"
```
Expected: `7 current sources registered`

**Step 5: Commit**

```bash
git add fetch_draft_picks/scraper.py
git commit -m "feat: scraper source registry and base interface"
```

---

## Task 9: scraper.py — Real Parse Functions + Claude Fallback

This task has two parts: (A) implement real parse functions after site inspection, (B) implement the Claude HTML fallback.

**Files:**
- Modify: `fetch_draft_picks/scraper.py`

### Part A — Real Parse Functions

After completing the site inspection in Task 8 Step 1, replace each `raise NotImplementedError` stub with a real BeautifulSoup parser. The pattern for each will follow this template:

```python
def _parse_tankathon_current(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    picks = []
    # TODO: replace selector with what you found during site inspection
    rows = soup.select("SELECTOR_HERE")
    for i, row in enumerate(rows, 1):
        cells = row.select("td")
        # Extract team name and abbr from cells — exact indices depend on site
        team_name = cells[INDEX].get_text(strip=True)
        abbr = _normalize_abbr(team_name)
        picks.append({
            "overall": i,
            "round": _round_for_overall(i),
            "pick_in_round": _pick_in_round(i),
            "team": team_name,
            "abbr": abbr,
            "is_comp": False,  # set True if comp pick column indicates it
            "original_team": team_name,  # update if traded pick column present
        })
    return picks
```

Add these helper functions to scraper.py:

```python
# Team name → abbreviation mapping (extend as needed)
_TEAM_ABBR = {
    "Las Vegas Raiders": "LV", "New York Jets": "NYJ", "Arizona Cardinals": "ARI",
    "Tennessee Titans": "TEN", "New York Giants": "NYG", "Cleveland Browns": "CLE",
    "Washington Commanders": "WSH", "New Orleans Saints": "NO",
    "Chicago Bears": "CHI", "New England Patriots": "NE", "Jacksonville Jaguars": "JAX",
    "Los Angeles Rams": "LAR", "Atlanta Falcons": "ATL", "Carolina Panthers": "CAR",
    "Pittsburgh Steelers": "PIT", "Philadelphia Eagles": "PHI",
    "Dallas Cowboys": "DAL", "Indianapolis Colts": "IND", "Cincinnati Bengals": "CIN",
    "Miami Dolphins": "MIA", "Seattle Seahawks": "SEA", "Denver Broncos": "DEN",
    "Tampa Bay Buccaneers": "TB", "Green Bay Packers": "GB", "Minnesota Vikings": "MIN",
    "Los Angeles Chargers": "LAC", "Detroit Lions": "DET", "San Francisco 49ers": "SF",
    "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF", "Kansas City Chiefs": "KC",
    "Houston Texans": "HOU",
}

def _normalize_abbr(team_name: str) -> str:
    for full, abbr in _TEAM_ABBR.items():
        if full.lower() in team_name.lower() or abbr.lower() == team_name.lower():
            return abbr
    return team_name.upper()[:3]  # fallback

def _round_for_overall(overall: int) -> int:
    # 32 teams, 7 rounds; comp picks extend later rounds
    thresholds = [32, 64, 96, 128, 160, 192, 224, 999]
    for i, t in enumerate(thresholds, 1):
        if overall <= t:
            return i
    return 7

def _pick_in_round(overall: int) -> int:
    return ((overall - 1) % 32) + 1
```

Implement all six parse functions (3 current, 3 future) following the same pattern.

**Test each parser manually against live HTML before moving on:**

```bash
python3 -c "
import requests
from fetch_draft_picks.scraper import HEADERS, _parse_espn_current
html = requests.get('https://www.espn.com/nfl/draft/rounds/_/season/2026', headers=HEADERS).text
picks = _parse_espn_current(html)
print(f'{len(picks)} picks parsed')
print(picks[:3])
"
```

Repeat for each source. Fix parsing until output looks correct.

### Part B — Claude HTML Fallback

When Python parsing fails, fetch the raw HTML, strip it to readable text, and send to Claude Haiku for extraction.

```python
import anthropic as _anthropic

_FALLBACK_PROMPT_CURRENT = """\
Extract the 2026 NFL draft pick order from the following webpage text.
Return ONLY a JSON array where each element has:
  overall (int), round (int), pick_in_round (int),
  team (string, full name), abbr (string, 2-3 letter code),
  is_comp (bool), original_team (string, full name before any trade).
Include all picks. If a pick was traded, set original_team to the team that originally owned it.

Webpage text:
{text}
"""

_FALLBACK_PROMPT_FUTURE = """\
Extract future traded NFL draft picks from the following webpage text.
Return ONLY a JSON array where each element has:
  year (int), round (int), original_abbr (string), current_abbr (string).
Only include picks where ownership has changed (traded picks).

Webpage text:
{text}
"""

def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())[:12000]  # cap tokens


def scrape_with_claude_fallback(source: Source) -> dict:
    """Fetch HTML and use Claude Haiku to extract structured pick data."""
    import anthropic
    t0 = time.time()
    try:
        html = fetch_html(source.url)
        text = _html_to_text(html)
        prompt_template = (
            _FALLBACK_PROMPT_CURRENT if source.mode == "current"
            else _FALLBACK_PROMPT_FUTURE
        )
        prompt = prompt_template.format(text=text)
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        import json
        picks = json.loads(raw)
        elapsed = round(time.time() - t0, 1)
        logger.info(
            "[scraper] %-30s OK  (claude-haiku)   %.1fs",
            source.name, elapsed,
        )
        return {"source": source.name, "picks": picks, "method": "claude-haiku",
                "elapsed": elapsed, "error": None}
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        logger.error("[scraper] %-30s FAIL (claude fallback also failed): %s",
                     source.name, e)
        return {"source": source.name, "picks": None, "method": "claude-haiku",
                "elapsed": elapsed, "error": str(e)}


def scrape_all_sources(sources: list[Source]) -> list[dict]:
    """Scrape all sources; fall back to Claude if Python parsing fails."""
    results = []
    for source in sorted(sources, key=lambda s: s.priority):
        result = scrape_source(source)
        if result["picks"] is None:
            print(f"  Python scraping failed for {source.name}, trying Claude fallback...")
            result = scrape_with_claude_fallback(source)
        results.append(result)
    return results
```

**Step: Verify end-to-end scrape (one source)**

```bash
python3 -c "
from fetch_draft_picks.scraper import CURRENT_SOURCES, scrape_all_sources
results = scrape_all_sources(CURRENT_SOURCES[:1])
print(results[0]['method'], len(results[0]['picks'] or []), 'picks')
"
```
Expected: `python 257 picks` (or similar) — or `claude-haiku N picks` if fallback triggered.

**Step: Commit**

```bash
git add fetch_draft_picks/scraper.py
git commit -m "feat: implement site parsers and Claude HTML fallback"
```

---

## Task 10: __main__.py — CLI, Orchestration, and Approval Loop

**Files:**
- Modify: `fetch_draft_picks/__main__.py`

**Step 1: Implement the full orchestrator**

```python
"""__main__.py — CLI entry point for fetch_draft_picks."""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .scraper import (
    CURRENT_SOURCES, FUTURE_SOURCES, NEWS_URLS,
    scrape_all_sources, _fetch_news_snippets,
)
from .differ import (
    diff_current_picks, compare_current_to_existing,
    diff_future_picks, compare_future_to_existing,
)
from .analyzer import analyze_conflicts
from .deployer import archive_json, upload_files

REPO_ROOT  = Path(__file__).parent.parent
JSON_DIR   = REPO_ROOT / "json"
ARCHIVE_DIR = JSON_DIR / "archive"
CURRENT_JSON = JSON_DIR / "draft_order_current.json"
FUTURE_JSON  = JSON_DIR / "future_pick_trades.json"


# ── Logging ──────────────────────────────────────────────────────────────────
from logging.handlers import RotatingFileHandler
_LOG_PATH = os.path.expanduser("~/Desktop/pickswap logs/fetch_draft_picks.log")
os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
_handler = RotatingFileHandler(_LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=5)
_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
_root_logger = logging.getLogger("fetch_draft_picks")
_root_logger.setLevel(logging.INFO)
_root_logger.addHandler(_handler)
logger = logging.getLogger("fetch_draft_picks.main")


# ── Approval loop ─────────────────────────────────────────────────────────────

def _print_separator():
    print("\n" + "━" * 54)

def _print_current_change(change: dict, idx: int, total: int, ai: dict):
    _print_separator()
    overall = change["overall"]
    print(f"PROPOSED CHANGE  [{idx} of {total}]")
    _print_separator()
    print(f"Pick #{overall}  (Round {change.get('round','?')}, "
          f"Pick {change.get('pick_in_round','?')})")
    curr = change.get("current")
    prop = change["proposed"]
    if curr:
        print(f"  Current:   team={curr['team']}, abbr={curr['abbr']}")
    else:
        print("  Current:   (new pick slot)")
    print(f"  Proposed:  team={prop['team']}, abbr={prop['abbr']}", end="")
    if prop.get("original_team") and prop["original_team"] != prop["team"]:
        print(f"  (original: {prop['original_team']})", end="")
    print()
    key = str(overall)
    if key in ai:
        a = ai[key]
        print(f"\nAI Analysis ({a.get('confidence','?')} confidence):")
        print(f"  {a.get('summary','')}")

def _print_future_change(change: dict, idx: int, total: int, ai: dict):
    _print_separator()
    print(f"PROPOSED CHANGE  [{idx} of {total}]")
    _print_separator()
    action = change["action"]
    if action == "add":
        print(f"ADD traded pick: {change['year']} R{change['round']} "
              f"{change['original_abbr']} → {change['current_abbr']}")
    elif action == "update":
        print(f"UPDATE {change['year']} R{change['round']} "
              f"(orig: {change['original_abbr']})")
        c = change["current_abbr"]
        print(f"  Current owner:  {c['current']}")
        print(f"  Proposed owner: {c['proposed']}")
    elif action == "remove":
        print(f"REMOVE traded pick: {change['year']} R{change['round']} "
              f"{change['original_abbr']} → {change['current_abbr']}")
    key = f"{change.get('year')}_{change.get('round')}_{change.get('original_abbr')}"
    if key in ai:
        a = ai[key]
        print(f"\nAI Analysis ({a.get('confidence','?')} confidence):")
        print(f"  {a.get('summary','')}")

def _prompt_user() -> str:
    while True:
        choice = input("\n[A]ccept  [R]eject  [S]kip  [Q]uit  > ").strip().upper()
        if choice in ("A", "R", "S", "Q"):
            return choice
        print("  Please enter A, R, S, or Q.")

def run_approval_loop(changes: list[dict], ai: dict, mode: str) -> list[dict] | None:
    """Interactive approval loop. Returns accepted changes, or None if user quit."""
    accepted, rejected, skipped = [], [], []
    pending = list(changes)

    while pending:
        total = len(pending)
        next_pending = []
        for i, change in enumerate(pending, 1):
            if mode == "current":
                _print_current_change(change, i, total, ai)
            else:
                _print_future_change(change, i, total, ai)
            choice = _prompt_user()
            if choice == "Q":
                print("\nQuitting. No changes written.")
                return None
            elif choice == "A":
                accepted.append(change)
                logger.info("[change] ACCEPTED %s", change)
            elif choice == "R":
                rejected.append(change)
                logger.info("[change] REJECTED %s", change)
            elif choice == "S":
                next_pending.append(change)

        if next_pending:
            print(f"\n{len(next_pending)} item(s) skipped. Review now? [Y/N] ", end="")
            if input().strip().upper() == "Y":
                pending = next_pending
            else:
                print(f"Skipping {len(next_pending)} item(s). They will not be written.")
                pending = []
        else:
            pending = []

    print(f"\n  Accepted: {len(accepted)}  Rejected: {len(rejected)}")
    return accepted


# ── Apply changes to JSON ──────────────────────────────────────────────────────

def apply_current_changes(accepted: list[dict], existing: dict) -> dict:
    idx = {p["overall"]: p for p in existing["picks"]}
    for change in accepted:
        overall = change["overall"]
        if change.get("current") is None:
            idx[overall] = change["proposed"]
        else:
            idx[overall].update(change["proposed"])
    updated_picks = [idx[k] for k in sorted(idx)]
    existing["picks"] = updated_picks
    existing["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return existing

def apply_future_changes(accepted: list[dict], existing: dict) -> dict:
    from .differ import _future_key
    idx = {_future_key(p): p for p in existing["traded_picks"]}
    for change in accepted:
        key = (change.get("year"), change.get("round"), change.get("original_abbr"))
        if change["action"] == "add":
            idx[key] = {k: change[k] for k in ("year","round","original_abbr","current_abbr")}
        elif change["action"] == "update":
            idx[key]["current_abbr"] = change["current_abbr"]["proposed"]
        elif change["action"] == "remove":
            idx.pop(key, None)
    existing["traded_picks"] = list(idx.values())
    existing["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return existing


# ── Source accuracy logging ────────────────────────────────────────────────────

def log_source_accuracy(scrape_results: list[dict], accepted: list[dict], mode: str):
    """Log whether each source agreed with the final accepted values."""
    if mode == "current":
        accepted_abbrs = {c["overall"]: c["proposed"]["abbr"] for c in accepted}
        for res in scrape_results:
            if not res["picks"]:
                continue
            for pick in res["picks"]:
                overall = pick.get("overall")
                if overall in accepted_abbrs:
                    agreed = pick.get("abbr") == accepted_abbrs[overall]
                    logger.info(
                        "[source-accuracy] %-25s agreed_with_accepted=%-5s pick=%s",
                        res["source"], agreed, overall,
                    )


# ── Main orchestration ─────────────────────────────────────────────────────────

def run_current(dry_run: bool = False):
    print("\n=== Current Year Draft Order ===")
    print("Scraping sources...")
    results = scrape_all_sources(CURRENT_SOURCES)
    successful = {r["source"]: r["picks"] for r in results if r["picks"]}

    if len(successful) < 2:
        print(f"  ERROR: Only {len(successful)} source(s) returned data. Need ≥2 to diff.")
        sys.exit(1)

    print(f"  {len(successful)} sources scraped successfully.")
    cross_conflicts = diff_current_picks(successful)
    print(f"  Cross-source conflicts: {len(cross_conflicts)}")
    for c in cross_conflicts:
        logger.info("[conflict] Pick#%s round=%s: %s", c["overall"], c["round"],
                    {k: v["abbr"] for k, v in c["values"].items()})

    with open(CURRENT_JSON) as f:
        existing = json.load(f)

    # Use majority vote as consensus
    consensus = _majority_vote_current(successful)
    changes = compare_current_to_existing(consensus, existing["picks"])
    print(f"  Proposed changes vs existing JSON: {len(changes)}")

    if not changes:
        print("  No changes needed.")
        return

    ai = {}
    if cross_conflicts:
        print("\nFetching news snippets for AI analysis...")
        news = _fetch_news_snippets(NEWS_URLS)
        ai = analyze_conflicts(cross_conflicts, news, mode="current")

    if dry_run:
        print("\n[Dry run] Changes that would be proposed:")
        for c in changes:
            print(f"  Pick#{c['overall']}: {c.get('current',{}).get('abbr','NEW')} → {c['proposed']['abbr']}")
        return

    accepted = run_approval_loop(changes, ai, mode="current")
    if accepted is None or not accepted:
        return

    log_source_accuracy(results, accepted, mode="current")

    date_str = datetime.now().strftime("%Y-%m-%d")
    archive_path = archive_json(CURRENT_JSON, ARCHIVE_DIR, date_str)
    print(f"\n  Archived → {archive_path.name}")

    updated = apply_current_changes(accepted, existing)
    with open(CURRENT_JSON, "w") as f:
        json.dump(updated, f, indent=2, ensure_ascii=False)
    print(f"  Written → {CURRENT_JSON.name}")

    _maybe_upload([str(CURRENT_JSON), str(archive_path)])


def run_future(dry_run: bool = False):
    print("\n=== Future Pick Trades ===")
    print("Scraping sources...")
    results = scrape_all_sources(FUTURE_SOURCES)
    successful = {r["source"]: r["picks"] for r in results if r["picks"]}

    if len(successful) < 2:
        print(f"  ERROR: Only {len(successful)} source(s) returned data. Need ≥2.")
        sys.exit(1)

    cross_conflicts = diff_future_picks(successful)
    print(f"  Cross-source conflicts: {len(cross_conflicts)}")
    for c in cross_conflicts:
        logger.info("[conflict] Future %s R%s %s: %s",
                    c["year"], c["round"], c["original_abbr"], c["values"])

    with open(FUTURE_JSON) as f:
        existing = json.load(f)

    consensus = _majority_vote_future(successful)
    changes = compare_future_to_existing(consensus, existing["traded_picks"])
    print(f"  Proposed changes vs existing JSON: {len(changes)}")

    if not changes:
        print("  No changes needed.")
        return

    ai = {}
    if cross_conflicts:
        print("\nFetching news snippets for AI analysis...")
        news = _fetch_news_snippets(NEWS_URLS)
        ai = analyze_conflicts(cross_conflicts, news, mode="future")

    if dry_run:
        for c in changes:
            print(f"  {c['action'].upper()} {c.get('year')} R{c.get('round')} "
                  f"{c.get('original_abbr')}")
        return

    accepted = run_approval_loop(changes, ai, mode="future")
    if accepted is None or not accepted:
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    archive_path = archive_json(FUTURE_JSON, ARCHIVE_DIR, date_str)
    print(f"\n  Archived → {archive_path.name}")

    updated = apply_future_changes(accepted, existing)
    with open(FUTURE_JSON, "w") as f:
        json.dump(updated, f, indent=2, ensure_ascii=False)
    print(f"  Written → {FUTURE_JSON.name}")

    _maybe_upload([str(FUTURE_JSON), str(archive_path)])


def _majority_vote_current(sources: dict[str, list[dict]]) -> list[dict]:
    """For each overall slot, pick the value held by the majority of sources."""
    from collections import Counter
    all_overalls = sorted({p["overall"] for picks in sources.values() for p in picks})
    result = []
    for overall in all_overalls:
        candidates = [
            next((p for p in picks if p["overall"] == overall), None)
            for picks in sources.values()
        ]
        candidates = [c for c in candidates if c]
        abbr_counts = Counter(c["abbr"] for c in candidates)
        winner_abbr = abbr_counts.most_common(1)[0][0]
        winner = next(c for c in candidates if c["abbr"] == winner_abbr)
        result.append(winner)
    return result


def _majority_vote_future(sources: dict[str, list[dict]]) -> list[dict]:
    from collections import Counter
    from .differ import _future_key
    all_keys = {_future_key(p) for picks in sources.values() for p in picks}
    result = []
    for key in sorted(all_keys):
        candidates = [
            next((p for p in picks if _future_key(p) == key), None)
            for picks in sources.values()
        ]
        candidates = [c for c in candidates if c]
        curr_counts = Counter(c["current_abbr"] for c in candidates)
        winner_curr = curr_counts.most_common(1)[0][0]
        year, round_, orig = key
        result.append({"year": year, "round": round_,
                        "original_abbr": orig, "current_abbr": winner_curr})
    return result


def _maybe_upload(paths: list[str]):
    print("\nReady to upload to Bluehost:")
    for p in paths:
        print(f"  → {p}")
    choice = input("\nUpload now? [Y]es / [N]o  > ").strip().upper()
    if choice == "Y":
        results = upload_files(paths)
        for r in results:
            status = "OK" if r["success"] else f"FAILED ({r['error']})"
            print(f"  {status} → {r['remote']}")
            if not r["success"]:
                logger.error("[upload] FAILED %s: %s", r["remote"], r["error"])
    else:
        print("  Upload skipped. Local files updated.")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape NFL draft pick data and update JSON files."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--current", action="store_true", help="Update current year draft order")
    group.add_argument("--future",  action="store_true", help="Update future pick trades")
    group.add_argument("--all",     action="store_true", help="Update both")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show proposed changes without writing or uploading")
    args = parser.parse_args()

    try:
        if args.current or args.all:
            run_current(dry_run=args.dry_run)
        if args.future or args.all:
            run_future(dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\nInterrupted. No changes written.")
        sys.exit(0)
    except Exception as e:
        logger.error("Unhandled exception: %s", e, exc_info=True)
        raise

    print("\nDone.")


if __name__ == "__main__":
    main()
```

**Step 2: Test with dry run (no files modified)**

```bash
python3 -m fetch_draft_picks --current --dry-run
```
Expected: Scraping output, then list of proposed changes (or "No changes needed."). No files written.

**Step 3: Commit**

```bash
git add fetch_draft_picks/__main__.py
git commit -m "feat: CLI orchestrator and interactive approval loop"
```

---

## Task 11: Integration Smoke Test

**Step 1: Run full flow with --dry-run**

```bash
python3 -m fetch_draft_picks --all --dry-run
```
Expected: Both current and future modes run, scraping succeeds, proposed changes listed, no files written.

**Step 2: Check the log**

```bash
tail -40 ~/Desktop/pickswap\ logs/fetch_draft_picks.log
```
Expected: Source scrape results, any conflicts, model selection (if conflicts exist).

**Step 3: Run unit test suite**

```bash
pytest tests/ -v
```
Expected: All tests PASS.

**Step 4: Run a real update (one change only)**

If confident in the data, run without `--dry-run` on one mode, accept one change, and verify the JSON file is updated and the archive exists:

```bash
python3 -m fetch_draft_picks --current
ls json/archive/
```

**Step 5: Final commit**

```bash
git add .
git commit -m "feat: fetch_draft_picks tool complete"
```

---

## Appendix: Adding a New Source Later

1. Write a `_parse_newsite_X(html: str) -> list[dict]` function in `scraper.py`
2. Add a `Source(...)` entry to `CURRENT_SOURCES` or `FUTURE_SOURCES`
3. Re-run — source accuracy will appear in the log automatically

## Appendix: Evaluating Source Quality

```bash
grep "source-accuracy" ~/Desktop/pickswap\ logs/fetch_draft_picks.log | \
  awk '{print $5, $6}' | sort | uniq -c | sort -rn
```

This shows how often each source agreed with your accepted values across all runs.
