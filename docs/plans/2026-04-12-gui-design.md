# GUI Design — NFL Draft Pick Updater

**Date:** 2026-04-12
**Status:** Approved

---

## Goal

Replace the CLI approval loop with a PyQt6 desktop app. The existing `fetch_draft_picks/` package is untouched — the GUI imports and calls it. No logic duplication.

---

## Architecture

Single `QMainWindow` with a `QStackedWidget` containing three panels that swap in place. Scraping runs on a `QThread` worker so the UI stays fully responsive throughout.

### File structure

```
gui/
  __init__.py
  app.py            ← QApplication entry point  →  python3 -m gui
  main_window.py    ← QMainWindow + QStackedWidget
  panels/
    launch.py       ← Panel 0: run options
    scraping.py     ← Panel 1: source grid + log
    review.py       ← Panel 2: one change at a time
  worker.py         ← QThread: scrape → diff → analyze, emits signals
  styles.py         ← Qt stylesheet (dark theme, consistent colors)
```

---

## Panel 0 — Launch

Compact window (~400×300). The obvious thing to do is click Run.

```
┌─────────────────────────────────────┐
│        NFL Draft Pick Updater        │
│                                      │
│  Mode                                │
│  ○ Current Year  ○ Future Picks      │
│  ○ Both                              │
│                                      │
│  [ ] Dry Run (preview only)          │
│                                      │
│         [ ▶  Run ]                   │
└─────────────────────────────────────┘
```

- Radio buttons: Current Year / Future Picks / Both
- Dry Run checkbox — when checked, Run button label becomes `▶ Preview`
- Run button is large and centered

---

## Panel 1 — Scraping

Replaces Launch panel immediately on Run. Expands vertically to fit grid + log.

```
┌─────────────────────────────────────────┐
│  Scraping sources...          [Cancel]  │
│                                         │
│  Source             Method   Time  St   │
│  ──────────────────────────────────── │
│  ⏳ espn            —        —          │
│  ✓  tankathon       python   2.1s       │
│  ⚠  nfldraftbuzz    haiku    4.3s       │
│  ⏳ pro-football-ref —       —          │
│  ...                                    │
│                                         │
│  ──────────────────────────────────── │
│  [▼ Log]                                │
│  13:42:01  INFO  tankathon OK 2.1s      │
│  13:42:03  WARN  nfldraftbuzz→fallback  │
│  13:42:05  INFO  haiku OK 4.3s          │
└─────────────────────────────────────────┘
```

- All source rows pre-populated with ⏳ at start
- Each row updates live: icon (✓ / ⚠ / ✗), method, elapsed time
- Log panel collapsed by default; `▼ Log` toggles it open
- Log contains full detail — every line the worker emits
- Cancel button sets a threading event the worker checks between sources
- On completion: auto-transitions to Review, or shows "No changes needed" dialog → back to Launch

---

## Panel 2 — Review

One change at a time. Replaces Scraping panel when changes are ready.

```
┌─────────────────────────────────────────┐
│  Review Changes  [2 of 7]               │
│                                         │
│  Pick #14  —  Round 1, Pick 14          │
│  ┌───────────────────────────────────┐  │
│  │ Current:   New England   NE       │  │
│  │ Proposed:  Indianapolis  IND      │  │
│  └───────────────────────────────────┘  │
│                                         │
│  AI Analysis  (high confidence)         │
│  Colts acquired this pick from          │
│  Patriots in the Jones trade, Apr 9.    │
│                                         │
│  [ Accept ]  [ Reject ]  [ Skip ]       │
│                                 [Quit]  │
└─────────────────────────────────────────┘
```

- Counter shows position (N of Total)
- Change card: current and proposed team + abbr
- AI Analysis block shown only when analysis is available
- Accept / Reject / Skip are equal-weight buttons
- Quit is small and right-aligned — intentionally de-emphasized
- After last change: summary dialog ("Accepted 5, Rejected 2") with "Write & Upload" button

---

## Threading & Data Flow

### Worker signals

```python
source_updated(name: str, method: str, elapsed: float, status: str)
log_message(level: str, text: str)
scrape_complete(changes: list, ai_results: dict)
error(message: str)
```

### Flow

```
[Launch panel]
  User clicks Run → worker.start()

[Scraping panel shown]
  worker emits source_updated() × N  → grid rows update live
  worker emits log_message() × N     → log appends
  worker emits scrape_complete()     → stack switches to Review panel
                                       (or "No changes" dialog → back to Launch)

[Review panel]
  Accept / Reject / Skip             → local list updated, next change shown
  Write & Upload                     → second short worker: apply_changes + SCP
  Quit                               → back to Launch, nothing written
```

The UI thread never blocks. Cancel sets a `threading.Event` the worker checks between sources.

---

## Dependencies

```
PyQt6>=6.6
```

Add to `requirements.txt`. No other new dependencies.

---

## Launch command

```bash
pip3 install PyQt6
python3 -m gui
```
