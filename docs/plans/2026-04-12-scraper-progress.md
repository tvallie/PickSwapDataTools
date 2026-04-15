# Draft Pick Scraper — Implementation Progress

**Plan file:** `docs/plans/2026-04-10-draft-pick-scraper.md`  
**Last updated:** 2026-04-12  
**Branch:** `main` (solo dev, no worktree)  
**Test status:** 17/17 passing

---

## To Resume

Tell Claude:

> "Use the superpowers:executing-plans skill to continue implementing the plan at `docs/plans/2026-04-10-draft-pick-scraper.md` — Tasks 1–6 are done, pick up at Task 7."

---

## Completed — Tasks 1–6

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Package scaffold | `fc96fda` | `fetch_draft_picks/__init__.py`, `__main__.py`, `scraper.py`, `differ.py`, `analyzer.py`, `deployer.py`, `requirements.txt`, `tests/__init__.py`, `tests/test_differ.py`, `tests/test_analyzer.py`, `tests/test_deployer.py` |
| 2 | differ.py — current picks diff | `00beef6` | `fetch_draft_picks/differ.py`, `tests/test_differ.py` |
| 3 | differ.py — future picks diff | `0e7b2b5` | `fetch_draft_picks/differ.py`, `tests/test_differ.py` |
| 4 | analyzer.py — model selection | `4e97ef3` | `fetch_draft_picks/analyzer.py`, `tests/test_analyzer.py` |
| 5 | analyzer.py — Claude API integration | `3c5fd97` | `fetch_draft_picks/analyzer.py`, `tests/test_analyzer.py` |
| 6 | deployer.py — JSON archiving | `33f43ed` | `fetch_draft_picks/deployer.py`, `tests/test_deployer.py` |

### What's implemented

- **`differ.py`** — `diff_current_picks`, `compare_current_to_existing`, `diff_future_picks`, `compare_future_to_existing`, `_future_key`
- **`analyzer.py`** — `select_model` (Haiku/Sonnet/Opus tiering by conflict count + stakes), `analyze_conflicts` (Claude API call with prompt templates for current/future modes)
- **`deployer.py`** — `archive_json` (copies JSON to `archive/` with date suffix; handles filename collisions)

---

## Remaining — Tasks 7–10

### Task 7: deployer.py — SCP Upload

Add `upload_files` to `fetch_draft_picks/deployer.py` and tests to `tests/test_deployer.py`.

Tests mock `subprocess.run`. Implementation:
- SSH host: `67.20.76.241`, user: `vallieor`, key: `~/.ssh/id_ed25519`
- Remote path: `public_html/website_3650ab54/json`
- Archive files go to `.../json/archive/`
- Full implementation is in the plan at Task 7, Step 3.

---

### Task 8: scraper.py — Source Registry and Base Interface

Implement `fetch_draft_picks/scraper.py` with:
- `Source` dataclass, `HEADERS`, `fetch_html`, `scrape_source`
- Stub parse functions for all 7 current + 4 future sources
- `CURRENT_SOURCES`, `FUTURE_SOURCES`, `NEWS_URLS` registries
- `_fetch_news_snippets`

**⚠️ Requires manual browser inspection of these URLs before Task 9:**

*Current picks:*
- `https://www.espn.com/nfl/draft/rounds/_/season/2026`
- `https://www.nfldraftbuzz.com/DraftOrder/2026`
- `https://www.tankathon.com/nfl/full_draft`
- `https://prosportstransactions.com/football/DraftTrades/Years/2026.htm`
- `https://www.si.com/nfl/updated-2026-nfl-draft-order-full-list-of-picks-all-seven-rounds`
- `https://www.nflmockdraftdatabase.com/draft-order/2026-nfl-draft-order`
- `https://www.pro-football-reference.com/years/2026/draft.htm`

*Future picks:*
- `https://overthecap.com/draft`
- `https://www.tankathon.com/picks/future_picks`
- `https://www.nfltraderumors.co/future-draft-picks`
- `https://football.realgm.com/analysis/3656/NFL-Future-Draft-Picks-By-Team`

Verify with:
```bash
python3 -c "from fetch_draft_picks.scraper import CURRENT_SOURCES; print(len(CURRENT_SOURCES), 'current sources registered')"
# Expected: 7 current sources registered
```

---

### Task 9: scraper.py — Real Parse Functions + Claude Fallback

Two parts:

**Part A** — Replace each `raise NotImplementedError` stub with a real BeautifulSoup parser based on site inspection findings. Use helpers: `_TEAM_ABBR`, `_normalize_abbr`, `_round_for_overall`, `_pick_in_round`.

**Part B** — Implement Claude Haiku HTML fallback:
- `_html_to_text` (strips nav/script/style, caps at 12k chars)
- `scrape_with_claude_fallback` (fetches HTML → strips → sends to Haiku)
- `scrape_all_sources` (tries Python parser first, falls back to Claude)

Verify end-to-end:
```bash
python3 -c "
from fetch_draft_picks.scraper import CURRENT_SOURCES, scrape_all_sources
results = scrape_all_sources(CURRENT_SOURCES[:1])
print(results[0]['method'], len(results[0]['picks'] or []), 'picks')
"
```

---

### Task 10: __main__.py — CLI, Orchestration, and Approval Loop

Full implementation of `fetch_draft_picks/__main__.py`:

- Logging: rotating file at `~/Desktop/pickswap logs/fetch_draft_picks.log`
- `run_current(dry_run)` — scrape → diff → majority vote → compare to JSON → AI analysis → approval loop → archive → write → upload
- `run_future(dry_run)` — same flow for future traded picks
- `run_approval_loop` — interactive A/R/S/Q loop with skip re-review
- `apply_current_changes` / `apply_future_changes` — mutate existing JSON dicts
- `_majority_vote_current` / `_majority_vote_future` — consensus from multi-source results
- `_maybe_upload` — prompt then call `upload_files`
- `log_source_accuracy` — logs per-source agreement with accepted changes
- `main()` — argparse with `--current`, `--future`, `--all`, `--dry-run`

Verify with:
```bash
python3 -m fetch_draft_picks --current --dry-run
# Expected: scraping output + proposed changes (or "No changes needed.") — no files written
```

---

## Running All Tests

```bash
cd /Users/todd/CodingProjects/PickSwapDataTools
python3 -m pytest tests/ -v
```
