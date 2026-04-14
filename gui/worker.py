"""worker.py — QThread worker: scrape, diff, analyze; emits signals to UI."""
import json
import threading
from collections import Counter
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from fetch_draft_picks.scraper import (
    CURRENT_SOURCES, FUTURE_SOURCES, NEWS_URLS,
    scrape_source, scrape_with_claude_fallback,
    fetch_news_snippets,
)
from fetch_draft_picks.differ import (
    diff_current_picks, compare_current_to_existing,
    diff_future_picks, compare_future_to_existing,
)
from fetch_draft_picks.analyzer import analyze_conflicts

JSON_DIR     = Path("/Users/todd/CodingProjects/PickSwapWeb/json")
CURRENT_JSON = JSON_DIR / "draft_order_current.json"
FUTURE_JSON  = JSON_DIR / "future_pick_trades.json"

_VALID_MODES = {"current", "future", "both"}


class ScraperWorker(QThread):
    source_updated  = pyqtSignal(str, str, float, str)  # name, method, elapsed, status
    log_message     = pyqtSignal(str, str)               # level, text
    scrape_complete = pyqtSignal(list, dict)             # changes, ai_results
    error           = pyqtSignal(str)

    def __init__(self, mode: str, dry_run: bool = False, parent=None):
        if mode not in _VALID_MODES:
            raise ValueError(f"mode must be one of {_VALID_MODES}, got {mode!r}")
        super().__init__(parent)
        self.mode    = mode
        self.dry_run = dry_run
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        try:
            if self.mode in ("current", "both"):
                if not self._run_mode("current"):
                    return
            if not self._cancel.is_set() and self.mode in ("future", "both"):
                self._run_mode("future")
        except Exception as e:
            self.error.emit(str(e))

    def _run_mode(self, mode: str) -> bool:
        sources   = CURRENT_SOURCES if mode == "current" else FUTURE_SOURCES
        json_path = CURRENT_JSON    if mode == "current" else FUTURE_JSON

        self.log_message.emit("INFO", f"=== {mode.title()} picks ===")

        results = []
        for source in sorted(sources, key=lambda s: s.priority):
            if self._cancel.is_set():
                return False
            result = scrape_source(source)
            if result["picks"] is None:
                self.log_message.emit("WARN", f"{source.name}: python failed → Claude fallback")
                result = scrape_with_claude_fallback(source)

            status  = "ok" if result["picks"] else "error"
            method  = result["method"] or "—"
            elapsed = result["elapsed"] or 0.0
            self.source_updated.emit(str(source.name), method, elapsed, status)
            msg = f"{source.name}  {method}  {elapsed:.1f}s"
            if result["error"]:
                msg += f"  ERR: {result['error']}"
            self.log_message.emit("INFO" if status == "ok" else "WARN", msg)
            results.append(result)

        successful = {r["source"]: r["picks"] for r in results if r["picks"]}
        if len(successful) < 1:
            self.error.emit("No sources returned data — check your internet connection.")
            return False

        try:
            with open(json_path) as f:
                existing = json.load(f)
        except FileNotFoundError:
            self.error.emit(f"JSON file not found: {json_path}. Has the scraper been run before?")
            return False
        except json.JSONDecodeError as e:
            self.error.emit(f"Malformed JSON in {json_path}: {e}")
            return False

        if mode == "current":
            cross_conflicts = diff_current_picks(successful) if len(successful) >= 2 else []
            consensus       = self._majority_vote_current(successful) if len(successful) >= 2 \
                              else list(successful.values())[0]
            changes         = compare_current_to_existing(consensus, existing["picks"])
            # Annotate each change with what every source says for that pick
            existing_idx = {p["overall"]: p for p in existing["picks"]}
            for c in changes:
                overall       = c["overall"]
                proposed_abbr = c["proposed"]["abbr"]
                json_abbr     = existing_idx.get(overall, {}).get("abbr", "—")
                c["_json_abbr"] = json_abbr
                c["_source_verdicts"] = {
                    src: next((p["abbr"] for p in picks if p["overall"] == overall), None)
                    for src, picks in successful.items()
                }
        else:
            import datetime
            current_year = datetime.date.today().year
            # Strip current-year picks — they belong to current mode, not future
            filtered = {
                src: [p for p in picks if p.get("year", 0) > current_year]
                for src, picks in successful.items()
            }
            filtered = {src: picks for src, picks in filtered.items() if picks}
            if not filtered:
                self.log_message.emit("WARN", f"No future picks (year > {current_year}) found in scraped data.")
                self.scrape_complete.emit([], {})
                return True
            cross_conflicts = diff_future_picks(filtered) if len(filtered) >= 2 else []
            consensus       = self._majority_vote_future(filtered) if len(filtered) >= 2 \
                              else list(filtered.values())[0]
            changes         = compare_future_to_existing(consensus, existing["traded_picks"])

        src_count = len(successful)
        self.log_message.emit("INFO", f"Sources with data: {src_count}")
        if src_count < 2:
            self.log_message.emit("WARN", "Only 1 source — skipping cross-source diff, comparing directly to stored JSON")
        self.log_message.emit("INFO", f"Cross-source conflicts: {len(cross_conflicts)}")
        self.log_message.emit("INFO", f"Proposed changes: {len(changes)}")

        ai = {}
        if cross_conflicts and not self.dry_run:
            self.log_message.emit("INFO", "Fetching news + running AI analysis...")
            news = fetch_news_snippets(NEWS_URLS)
            ai   = analyze_conflicts(cross_conflicts, news, mode=mode)

        self.scrape_complete.emit(changes, ai)
        return True

    def _majority_vote_current(self, sources: dict) -> list:
        all_overalls = sorted({p["overall"] for picks in sources.values() for p in picks})
        result = []
        for overall in all_overalls:
            candidates = [
                next((p for p in picks if p["overall"] == overall), None)
                for picks in sources.values()
            ]
            candidates = [c for c in candidates if c]
            winner_abbr = Counter(c["abbr"] for c in candidates).most_common(1)[0][0]
            result.append(next(c for c in candidates if c["abbr"] == winner_abbr))
        return result

    def _majority_vote_future(self, sources: dict) -> list:
        from fetch_draft_picks.differ import _future_key  # private helper, same package
        all_keys = {_future_key(p) for picks in sources.values() for p in picks}
        result = []
        for key in sorted(all_keys):
            candidates = [
                next((p for p in picks if _future_key(p) == key), None)
                for picks in sources.values()
            ]
            candidates = [c for c in candidates if c]
            winner_curr = Counter(c["current_abbr"] for c in candidates).most_common(1)[0][0]
            year, round_, orig = key
            result.append({"year": year, "round": round_,
                            "original_abbr": orig, "current_abbr": winner_curr})
        return result
