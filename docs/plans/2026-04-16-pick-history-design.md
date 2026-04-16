# Pick History Design

**Date:** 2026-04-16
**Status:** Approved, pending implementation

---

## Goal

Track a running history of when NFL draft picks change hands — both current year picks (2026 draft order) and future traded picks (2027+). Each transaction records the date and the from/to teams.

---

## Approach: Two Separate History Files

Mirrors the existing JSON structure (`draft_order_current.json` / `future_pick_trades.json`). History lives in the same directory alongside live data.

**Files:**
- `PickSwapWeb/json/current_pick_history.json`
- `PickSwapWeb/json/future_pick_history.json`

---

## Data Format

### current_pick_history.json

```json
{
  "history": [
    {
      "overall": 13,
      "round": 1,
      "pick_in_round": 13,
      "date": "2026-04-15",
      "from": "ATL",
      "to": "LAR"
    }
  ]
}
```

### future_pick_history.json

```json
{
  "history": [
    {
      "year": 2027,
      "round": 1,
      "original_abbr": "GB",
      "date": "2026-04-15",
      "from": "GB",
      "to": "DAL"
    }
  ]
}
```

`original_abbr` is the permanent identifier for a future pick (the team that first owned it). `from` and `to` are the transacting teams for that specific change.

---

## When History Is Written

- Appended automatically during a write run when the user accepts changes in the review grid
- No separate approval — accepted = also written to history
- Date = date of the write run (same `date_str` used for JSON archiving)
- Entries are appended, never overwritten — the file grows over time

---

## Where to Hook In

- **GUI:** `main_window.py` → `_apply_and_write()` — after writing current/future JSON
- **CLI:** `__main__.py` → `apply_current_changes()` / `apply_future_changes()`
- New module: `fetch_draft_picks/historian.py` — handles both history files

---

## Edge Cases

- If history file doesn't exist yet, create it with an empty `history` array
- A pick can appear multiple times in history (each trade is its own entry)
- History files are archived to Bluehost alongside the live JSON files

---

## Phase 2: History Scraping + GUI Viewer

**Date:** 2026-04-16  
**Status:** Approved

### Goal

Scrape the full chain of pick ownership trades from `prosportstransactions.com`, show new entries for user approval in the existing review panel, and append approved entries to the history JSON files. Runs as a first-class mode alongside "Current Year" and "Future Picks" in the launch panel.

### New Sources in `scraper.py`

Two new `Source` entries using Playwright (same pattern as SI/RealGM):

- `prosportstransactions-current` — scrapes `.../DraftTrades/Years/2026.htm`
- `prosportstransactions-future` — scrapes `.../DraftTrades/Future/<Team>.htm` for all 32 teams

Each parse function returns a list of trade entries matching the existing history JSON format.

### Diff Logic

A new `diff_current_history` / `diff_future_history` function compares scraped entries against the existing history file and returns only entries not yet recorded. Deduplication key:

- Current: `(overall, date, from, to)`
- Future: `(year, round, original_abbr, date, from, to)`

### GUI Changes

**Launch panel** — new "View History" section below the existing scraping radio buttons, with two checkboxes:

- `[ ] Current Pick History`
- `[ ] Future Pick History`

When at least one is checked and Run is clicked, the history scrape flow runs instead of the normal scrape flow. The Run/Preview button label changes to "View History" when any history checkbox is checked.

**Review panel** — new `history_current`, `history_future`, and `history_both` modes. Columns:

- Current: `[✓]  Pick  Rnd  Date  From  To`
- Future: `[✓]  Year  Rnd  Original  Date  From  To`
- Both: `[✓]  Type  Pick/Year  Rnd  Original  Date  From  To`

"Apply Selected" appends approved entries to the history JSON files via `historian.py`. No writes to `draft_order_current.json` or `future_pick_trades.json`.

**`main_window.py`** — new `_run_history()` method: scrape → diff → load review panel. On approval, calls `historian.py` directly (bypasses `_apply_and_write`).

### Data Flow

```
Launch panel (history checkboxes checked)
  → _run_history()
  → scrape prosportstransactions.com (Playwright)
  → diff against existing history JSON
  → if no new entries: show message, return to launch
  → load ReviewPanel with new entries (history mode)
  → user approves subset
  → append_current_history() / append_future_history()
  → show confirmation, return to launch
```

### Error Handling

- Scrape fails / site unreachable: show error dialog, return to launch panel
- Zero new entries after diff: show "No new entries found" message, return to launch
- Partial failures (some entries unparseable): skip bad rows, log warnings, proceed with valid entries

### Testing

- `tests/test_history_differ.py` — unit tests for diff logic: new entries detected, exact duplicates skipped
- No unit tests for Playwright scraping (same policy as existing scrapers)

### Files Touched

| File | Change |
|------|--------|
| `fetch_draft_picks/scraper.py` | Add 2 new sources + parse functions |
| `fetch_draft_picks/differ.py` | Add `diff_current_history`, `diff_future_history` |
| `tests/test_history_differ.py` | New — diff unit tests |
| `gui/panels/launch.py` | Add history checkboxes section |
| `gui/panels/review.py` | Add history table modes |
| `gui/main_window.py` | Add `_run_history()` method |
