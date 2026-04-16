# Pick History Viewer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "View History" section to the launch panel that scrapes pick trade history from prosportstransactions.com, diffs against existing history files, and presents new entries for user approval in the review panel.

**Architecture:** New `CURRENT_HISTORY_SOURCES` / `FUTURE_HISTORY_SOURCES` lists in `scraper.py` re-use the existing `Source` / `scrape_source` infrastructure. New `diff_current_history` / `diff_future_history` in `differ.py` deduplicate against existing history JSON. `LaunchPanel` gets a new section with two checkboxes that emit a `history_requested` signal wired to a new `_run_history()` method in `main_window.py`. `ReviewPanel` gets a `load_history` method for read-only history table display.

**Tech Stack:** Python stdlib, BeautifulSoup, Playwright (already installed), PyQt6.

---

### Task 1: Diff logic for history entries

**Files:**
- Modify: `fetch_draft_picks/differ.py`
- Create: `tests/test_history_differ.py`

**Step 1: Write failing tests**

```python
# tests/test_history_differ.py
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
```

**Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_history_differ.py -v
```
Expected: `ImportError` — functions don't exist yet.

**Step 3: Implement diff functions**

Add to the bottom of `fetch_draft_picks/differ.py`:

```python
def diff_current_history(scraped: list[dict], existing: list[dict]) -> list[dict]:
    """Return scraped history entries not already in existing."""
    keys = {(e["overall"], e["date"], e["from"], e["to"]) for e in existing}
    return [e for e in scraped if (e["overall"], e["date"], e["from"], e["to"]) not in keys]


def diff_future_history(scraped: list[dict], existing: list[dict]) -> list[dict]:
    """Return scraped history entries not already in existing."""
    keys = {(e["year"], e["round"], e["original_abbr"], e["date"], e["from"], e["to"]) for e in existing}
    return [e for e in scraped if (e["year"], e["round"], e["original_abbr"], e["date"], e["from"], e["to"]) not in keys]
```

**Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_history_differ.py -v
```
Expected: all 8 tests PASS.

**Step 5: Run full suite**

```bash
python3 -m pytest tests/ -v
```
Expected: all tests PASS.

**Step 6: Commit**

```bash
git add fetch_draft_picks/differ.py tests/test_history_differ.py
git commit -m "feat: add history diff functions"
```

---

### Task 2: Inspect prosportstransactions.com HTML

**Files:**
- Create (temp): `scripts/inspect_prosports.py`

This is a discovery task — we can't write the parse functions without seeing the actual HTML structure.

**Step 1: Create inspection script**

```python
# scripts/inspect_prosports.py
"""Run once to inspect prosportstransactions.com HTML structure."""
from playwright.sync_api import sync_playwright

URLS = [
    "https://prosportstransactions.com/football/DraftTrades/Years/2026.htm",
    "https://prosportstransactions.com/football/DraftTrades/Years/2027.htm",
]

def inspect(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context().new_page()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        html = page.content()
        browser.close()
    # Print the first 4000 chars to see the structure
    print(f"\n{'='*60}\n{url}\n{'='*60}")
    print(html[:4000])

for url in URLS:
    inspect(url)
```

**Step 2: Run it and read the output**

```bash
mkdir -p scripts
python3 scripts/inspect_prosports.py 2>&1 | head -150
```

Read the output carefully. Look for:
- The HTML tag structure around the trade table (`<table>`, `<tr>`, `<td>`)
- Column names/order in the header row
- How pick details appear (e.g. "2026 1st round pick", "from ATL", "to LAR")
- The date format used
- How the team name or abbreviation appears

**Step 3: Identify the CSS selector or table structure**

Based on the output, note in a comment at the top of your parse function:
- Which table on the page contains trade data
- Which columns hold date, teams, pick description

**Step 4: Delete the temp script (do NOT commit it)**

```bash
rm scripts/inspect_prosports.py
rmdir scripts 2>/dev/null || true
```

---

### Task 3: Current history scraper

**Files:**
- Modify: `fetch_draft_picks/scraper.py`

> **Note:** No unit tests for scraper parse functions (project policy — same as all other sources).

**Step 1: Write `_parse_prosports_current(html)`**

Add this function in `scraper.py` before the source registry, after the other parse functions. Adapt the selectors based on what you found in Task 2. The function must return a list of dicts matching this shape:
```python
{"overall": int, "round": int, "pick_in_round": int, "date": "YYYY-MM-DD", "from": "ABR", "to": "ABR"}
```

Template to fill in (adapt column indices based on Task 2 findings):

```python
def _parse_prosports_current(html: str) -> list[dict]:
    """Parse prosportstransactions.com DraftTrades/Years/2026.htm.

    Table columns (verify against actual page — adjust indices if needed):
      0: Date  1: Approx  2: Team  3: Acquired  4: Relinquished  5: Notes
    Each traded pick appears as a pair of rows (one per team) or a single row.
    We extract entries where a pick changed hands: resolve team abbr, round, overall.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Find the main transactions table — adjust selector if needed
    table = soup.find("table", {"class": "datatable"}) or soup.find("table")
    if not table:
        logger.warning("[prosports-current] no table found")
        return results

    rows = table.find_all("tr")[1:]  # skip header
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cells) < 4:
            continue
        try:
            date_str  = cells[0]          # e.g. "2026-01-15"
            team_name = cells[2]          # e.g. "Los Angeles Rams"
            acquired  = cells[3]          # e.g. "2026 1st round pick (from ATL)"
            relinq    = cells[4] if len(cells) > 4 else ""

            # Skip rows that aren't pick trades
            if "round pick" not in acquired.lower() and "round pick" not in relinq.lower():
                continue

            # Parse the pick details from the description — adapt regex to match real text
            import re
            # Example pattern: "2026 1st round pick (from ATL)" or "2026 1st round pick (#13, from ATL)"
            m = re.search(
                r"(\d{4})\s+(\w+)\s+round pick(?:\s+\(#(\d+))?.*?\(from (\w+)\)",
                acquired, re.IGNORECASE
            )
            if not m:
                continue

            year       = int(m.group(1))
            round_word = m.group(2).lower()
            overall    = int(m.group(3)) if m.group(3) else 0
            from_abbr  = m.group(4).upper()
            to_abbr    = _team_abbr(team_name)  # use existing helper

            round_map = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4,
                         "5th": 5, "6th": 6, "7th": 7}
            rnd = round_map.get(round_word, 0)

            if year == 2026 and from_abbr and to_abbr and from_abbr != to_abbr:
                results.append({
                    "overall":       overall,
                    "round":         rnd,
                    "pick_in_round": 0,   # fill in if page has it; else 0
                    "date":          date_str,
                    "from":          from_abbr,
                    "to":            to_abbr,
                })
        except Exception as e:
            logger.debug("[prosports-current] skip row %s: %s", cells, e)

    logger.info("[prosports-current] parsed %d entries", len(results))
    return results
```

> **Important:** The regex and column indices above are guesses — adjust them based on what you saw in Task 2. Run the scraper manually after wiring it up (Task 7) to verify output.

**Step 2: Add `CURRENT_HISTORY_SOURCES` and `FUTURE_HISTORY_SOURCES` to the source registry**

At the bottom of `scraper.py`, after the existing registries:

```python
CURRENT_HISTORY_SOURCES = [
    Source(
        "prosportstransactions-current",
        "https://prosportstransactions.com/football/DraftTrades/Years/2026.htm",
        "history_current",
        _parse_prosports_current,
        priority=0,
        use_playwright=True,
    ),
]
```

**Step 3: Commit**

```bash
git add fetch_draft_picks/scraper.py
git commit -m "feat: add prosportstransactions current history scraper"
```

---

### Task 4: Future history scraper

**Files:**
- Modify: `fetch_draft_picks/scraper.py`

**Step 1: Write `_parse_prosports_future_history(html)`**

Add after `_parse_prosports_current` in `scraper.py`. Returns a list of dicts matching:
```python
{"year": int, "round": int, "original_abbr": "ABR", "date": "YYYY-MM-DD", "from": "ABR", "to": "ABR"}
```

Template (adapt based on Task 2 findings for the future-year pages):

```python
def _parse_prosports_future_history(html: str) -> list[dict]:
    """Parse prosportstransactions.com DraftTrades/Years/<year>.htm for future picks.

    Same table structure as current — only difference is we're looking for
    picks from years 2027+ instead of 2026.
    """
    from bs4 import BeautifulSoup
    import re
    soup = BeautifulSoup(html, "html.parser")
    results = []

    table = soup.find("table", {"class": "datatable"}) or soup.find("table")
    if not table:
        logger.warning("[prosports-future] no table found")
        return results

    rows = table.find_all("tr")[1:]
    for row in rows:
        cells = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cells) < 4:
            continue
        try:
            date_str  = cells[0]
            team_name = cells[2]
            acquired  = cells[3]
            if "round pick" not in acquired.lower():
                continue

            m = re.search(
                r"(\d{4})\s+(\w+)\s+round pick.*?\(from (\w+)\)",
                acquired, re.IGNORECASE
            )
            if not m:
                continue

            year       = int(m.group(1))
            round_word = m.group(2).lower()
            from_abbr  = m.group(3).upper()
            to_abbr    = _team_abbr(team_name)

            round_map = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4,
                         "5th": 5, "6th": 6, "7th": 7}
            rnd = round_map.get(round_word, 0)

            if year >= 2027 and from_abbr and to_abbr and from_abbr != to_abbr:
                results.append({
                    "year":          year,
                    "round":         rnd,
                    "original_abbr": from_abbr,   # original owner = who gave it up first
                    "date":          date_str,
                    "from":          from_abbr,
                    "to":            to_abbr,
                })
        except Exception as e:
            logger.debug("[prosports-future] skip row %s: %s", cells, e)

    logger.info("[prosports-future] parsed %d entries", len(results))
    return results
```

**Step 2: Add `FUTURE_HISTORY_SOURCES` to the registry**

```python
FUTURE_HISTORY_SOURCES = [
    Source(
        "prosportstransactions-future-2027",
        "https://prosportstransactions.com/football/DraftTrades/Years/2027.htm",
        "history_future",
        _parse_prosports_future_history,
        priority=0,
        use_playwright=True,
    ),
    Source(
        "prosportstransactions-future-2028",
        "https://prosportstransactions.com/football/DraftTrades/Years/2028.htm",
        "history_future",
        _parse_prosports_future_history,
        priority=1,
        use_playwright=True,
    ),
]
```

**Step 3: Commit**

```bash
git add fetch_draft_picks/scraper.py
git commit -m "feat: add prosportstransactions future history scraper"
```

---

### Task 5: Launch panel — history checkboxes

**Files:**
- Modify: `gui/panels/launch.py`

**Step 1: Add `history_requested` signal and checkbox widgets**

Current `__init__` has `run_requested = pyqtSignal(str, bool)`. Add a second signal and the two checkboxes. Here is the full updated file:

```python
"""launch.py — Panel 0: run options and launch button."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QRadioButton, QCheckBox, QPushButton, QLabel,
    QButtonGroup, QSpacerItem, QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt


class LaunchPanel(QWidget):
    run_requested     = pyqtSignal(str, bool)   # mode, dry_run
    history_requested = pyqtSignal(bool, bool)  # current_history, future_history

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(20)

        title = QLabel("NFL Draft Pick Updater")
        title.setObjectName("title_label")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        root.addSpacerItem(QSpacerItem(0, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # ── Scrape section ────────────────────────────────────────────────────
        mode_label = QLabel("Scrape")
        root.addWidget(mode_label)

        self._mode_group    = QButtonGroup(self)
        self._radio_current = QRadioButton("Current Year")
        self._radio_future  = QRadioButton("Future Picks")
        self._radio_current.setChecked(True)
        for i, rb in enumerate([self._radio_current, self._radio_future]):
            self._mode_group.addButton(rb, i)
            root.addWidget(rb)

        root.addSpacerItem(QSpacerItem(0, 6, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        self._dry_run_cb = QCheckBox("Dry Run (preview only, no files written)")
        self._dry_run_cb.setChecked(True)
        self._dry_run_cb.checkStateChanged.connect(self._update_button_label)
        root.addWidget(self._dry_run_cb)

        root.addSpacerItem(QSpacerItem(0, 10, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        # ── View History section ──────────────────────────────────────────────
        history_label = QLabel("View History")
        root.addWidget(history_label)

        self._history_current_cb = QCheckBox("Current Pick History")
        self._history_future_cb  = QCheckBox("Future Pick History")
        self._history_current_cb.checkStateChanged.connect(self._update_button_label)
        self._history_future_cb.checkStateChanged.connect(self._update_button_label)
        root.addWidget(self._history_current_cb)
        root.addWidget(self._history_future_cb)

        root.addSpacerItem(QSpacerItem(0, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._run_btn = QPushButton("▶  Preview")
        self._run_btn.setObjectName("run_btn")
        self._run_btn.clicked.connect(self._on_run)
        btn_row.addWidget(self._run_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        root.addStretch()

    def _history_mode(self) -> bool:
        return (self._history_current_cb.isChecked() or
                self._history_future_cb.isChecked())

    def _update_button_label(self):
        if self._history_mode():
            self._run_btn.setText("▶  View History")
        elif self._dry_run_cb.isChecked():
            self._run_btn.setText("▶  Preview")
        else:
            self._run_btn.setText("▶  Run")

    def _on_run(self):
        if self._history_mode():
            self.history_requested.emit(
                self._history_current_cb.isChecked(),
                self._history_future_cb.isChecked(),
            )
        else:
            mode_map = {0: "current", 1: "future"}
            mode = mode_map.get(self._mode_group.checkedId(), "current")
            self.run_requested.emit(mode, self._dry_run_cb.isChecked())
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```
Expected: all tests PASS.

**Step 3: Commit**

```bash
git add gui/panels/launch.py
git commit -m "feat: add history checkboxes to launch panel"
```

---

### Task 6: Review panel — history modes

**Files:**
- Modify: `gui/panels/review.py`

**Step 1: Add `load_history` method**

Add after `load_changes` in `ReviewPanel`:

```python
def load_history(self, entries: list[dict], mode: str):
    """Display new history entries for approval. mode: 'current', 'future', or 'both'."""
    self._changes = list(entries)
    self._mode    = f"history_{mode}"
    self._build_history_table(entries, mode)

def _build_history_table(self, entries: list[dict], mode: str):
    if mode == "current":
        headers = ["", "Pick", "Rnd", "Date", "From", "To"]
    elif mode == "future":
        headers = ["", "Year", "Rnd", "Original", "Date", "From", "To"]
    else:  # both
        headers = ["", "Type", "Pick/Year", "Rnd", "Original", "Date", "From", "To"]

    self._table.setColumnCount(len(headers))
    self._table.setRowCount(len(entries))
    self._table.setHorizontalHeaderLabels(headers)

    hdr = self._table.horizontalHeader()
    hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    self._table.setColumnWidth(0, 40)
    for col in range(1, len(headers)):
        hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
    # Stretch the last column
    hdr.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Stretch)

    left = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

    def cell(text, color=None):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if color:
            item.setForeground(QColor(color))
        return item

    def checkbox():
        item = QTableWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        item.setCheckState(Qt.CheckState.Checked)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    for row, e in enumerate(entries):
        self._table.setItem(row, 0, checkbox())
        if mode == "current":
            self._table.setItem(row, 1, cell(f"#{e.get('overall', '?')}"))
            self._table.setItem(row, 2, cell(f"R{e.get('round', '?')}"))
            self._table.setItem(row, 3, cell(e.get("date", "?")))
            self._table.setItem(row, 4, cell(e.get("from", "?"), color=RED))
            self._table.setItem(row, 5, cell(e.get("to", "?"),   color=GREEN))
        elif mode == "future":
            self._table.setItem(row, 1, cell(str(e.get("year", "?"))))
            self._table.setItem(row, 2, cell(f"R{e.get('round', '?')}"))
            self._table.setItem(row, 3, cell(e.get("original_abbr", "?")))
            self._table.setItem(row, 4, cell(e.get("date", "?")))
            self._table.setItem(row, 5, cell(e.get("from", "?"), color=RED))
            self._table.setItem(row, 6, cell(e.get("to", "?"),   color=GREEN))
        else:  # both
            kind = "Current" if "overall" in e else "Future"
            self._table.setItem(row, 1, cell(kind))
            pick_year = f"#{e['overall']}" if "overall" in e else str(e.get("year", "?"))
            self._table.setItem(row, 2, cell(pick_year))
            self._table.setItem(row, 3, cell(f"R{e.get('round', '?')}"))
            self._table.setItem(row, 4, cell(e.get("original_abbr", "—")))
            self._table.setItem(row, 5, cell(e.get("date", "?")))
            self._table.setItem(row, 6, cell(e.get("from", "?"), color=RED))
            self._table.setItem(row, 7, cell(e.get("to", "?"),   color=GREEN))

    self._table.resizeRowsToContents()
    self._table.setMinimumHeight(min(500, 60 + len(entries) * 28))
    self._lbl.setText(f"{len(entries)} new trade(s) found — check the ones to add to history:")
    self._counter.setText(f"{len(entries)} new")
```

**Step 2: Run tests**

```bash
python3 -m pytest tests/ -v
```
Expected: all tests PASS.

**Step 3: Commit**

```bash
git add gui/panels/review.py
git commit -m "feat: add history table mode to review panel"
```

---

### Task 7: Wire it all together in main_window.py

**Files:**
- Modify: `gui/main_window.py`

**Step 1: Add `history_requested` signal connection in `__init__`**

Find the line:
```python
self._launch.run_requested.connect(self._on_run)
```
Add after it:
```python
self._launch.history_requested.connect(self._on_history)
```

**Step 2: Add `_on_history` and `_run_history` methods**

Add after `_apply_and_write` in `main_window.py`:

```python
def _on_history(self, want_current: bool, want_future: bool):
    self._stack.setCurrentIndex(SCRAPING)
    self._scraping.set_status("Scraping pick history from prosportstransactions.com…")
    self._run_history(want_current, want_future)

def _run_history(self, want_current: bool, want_future: bool):
    from fetch_draft_picks.scraper       import scrape_all_sources, CURRENT_HISTORY_SOURCES, FUTURE_HISTORY_SOURCES
    from fetch_draft_picks.differ        import diff_current_history, diff_future_history
    from fetch_draft_picks.historian     import append_current_history, append_future_history
    import json

    date_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    new_entries = []

    if want_current:
        results = scrape_all_sources(CURRENT_HISTORY_SOURCES)
        scraped = [p for r in results if r["picks"] for p in r["picks"]]
        existing = json.loads(CURRENT_HISTORY.read_text()).get("history", []) if CURRENT_HISTORY.exists() else []
        new_entries += diff_current_history(scraped, existing)

    if want_future:
        results = scrape_all_sources(FUTURE_HISTORY_SOURCES)
        scraped = [p for r in results if r["picks"] for p in r["picks"]]
        existing = json.loads(FUTURE_HISTORY.read_text()).get("history", []) if FUTURE_HISTORY.exists() else []
        new_entries += diff_future_history(scraped, existing)

    if not new_entries:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "No New Entries", "No new history entries found.")
        self._stack.setCurrentIndex(LAUNCH)
        return

    if want_current and want_future:
        mode = "both"
    elif want_current:
        mode = "current"
    else:
        mode = "future"

    self._history_entries = new_entries
    self._history_mode_str = mode
    self._review.load_history(new_entries, mode)
    self._review.review_complete.connect(self._on_history_applied)
    self._stack.setCurrentIndex(REVIEW)
    self.resize(900, 600)

def _on_history_applied(self, accepted: list):
    from fetch_draft_picks.historian import append_current_history, append_future_history
    import datetime
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    current_accepted = [e for e in accepted if "overall" in e]
    future_accepted  = [e for e in accepted if "year" in e and "overall" not in e]

    if current_accepted:
        append_current_history(current_accepted, date_str, CURRENT_HISTORY)
    if future_accepted:
        append_future_history(future_accepted, date_str, FUTURE_HISTORY)

    try:
        self._review.review_complete.disconnect(self._on_history_applied)
    except Exception:
        pass

    self._go_to_launch()
```

**Step 3: Run tests**

```bash
python3 -m pytest tests/ -v
```
Expected: all tests PASS.

**Step 4: Smoke test the GUI**

```bash
python3 -m gui
```

- Check "Current Pick History" and/or "Future Pick History"
- Confirm the Run button changes to "▶  View History"
- Click it — confirm the scraping panel appears with the status message
- If prosportstransactions.com is reachable: confirm the review table populates
- If zero new entries: confirm the "No new entries" dialog appears and returns to launch

**Step 5: Commit**

```bash
git add gui/main_window.py
git commit -m "feat: wire history scrape flow into main window"
```
