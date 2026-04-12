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

REPO_ROOT    = Path(__file__).parent.parent
CURRENT_JSON = REPO_ROOT / "json" / "draft_order_current.json"
FUTURE_JSON  = REPO_ROOT / "json" / "future_pick_trades.json"

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
        if len(successful) < 2:
            self.error.emit(
                f"Only {len(successful)} source(s) returned data. Need ≥2 to diff."
            )
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
            cross_conflicts = diff_current_picks(successful)
            consensus       = self._majority_vote_current(successful)
            changes         = compare_current_to_existing(consensus, existing["picks"])
        else:
            cross_conflicts = diff_future_picks(successful)
            consensus       = self._majority_vote_future(successful)
            changes         = compare_future_to_existing(consensus, existing["traded_picks"])

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
