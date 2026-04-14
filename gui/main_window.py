"""main_window.py — QMainWindow with QStackedWidget panel management."""
import json
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox

from gui.panels.launch   import LaunchPanel
from gui.panels.scraping import ScrapingPanel
from gui.panels.review   import ReviewPanel
from gui.worker          import ScraperWorker
from gui.styles          import STYLESHEET
from fetch_draft_picks.scraper import CURRENT_SOURCES, FUTURE_SOURCES

REPO_ROOT    = Path(__file__).parent.parent
CURRENT_JSON = REPO_ROOT / "json" / "draft_order_current.json"
FUTURE_JSON  = REPO_ROOT / "json" / "future_pick_trades.json"
ARCHIVE_DIR  = REPO_ROOT / "json" / "archive"

LAUNCH, SCRAPING, REVIEW = 0, 1, 2


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NFL Draft Pick Updater")
        self.setMinimumSize(500, 420)
        self.setStyleSheet(STYLESHEET)
        self._worker: ScraperWorker | None = None
        self._mode    = "current"
        self._dry_run = False

        self._stack   = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._launch   = LaunchPanel()
        self._scraping = ScrapingPanel()
        self._review   = ReviewPanel()
        self._stack.addWidget(self._launch)
        self._stack.addWidget(self._scraping)
        self._stack.addWidget(self._review)

        self._launch.run_requested.connect(self._on_run)
        self._scraping.cancel_requested.connect(self._on_cancel)
        self._review.review_complete.connect(self._on_review_complete)
        self._review.quit_review.connect(self._go_to_launch)

        self._stack.setCurrentIndex(LAUNCH)

    def _on_run(self, mode: str, dry_run: bool):
        self._mode    = mode
        self._dry_run = dry_run

        if mode == "both":
            names = [s.name for s in CURRENT_SOURCES] + [s.name for s in FUTURE_SOURCES]
        elif mode == "current":
            names = [s.name for s in CURRENT_SOURCES]
        else:
            names = [s.name for s in FUTURE_SOURCES]

        self._scraping.reset(names)
        self._stack.setCurrentIndex(SCRAPING)
        self.resize(600, 520)

        self._worker = ScraperWorker(mode=mode, dry_run=dry_run)
        self._worker.source_updated.connect(self._scraping.on_source_updated)
        self._worker.log_message.connect(self._scraping.on_log_message)
        self._worker.scrape_complete.connect(self._on_scrape_complete)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_cancel(self):
        if self._worker:
            self._worker.cancel()
        self._go_to_launch()

    def _on_scrape_complete(self, changes: list, ai: dict):
        if not changes:
            QMessageBox.information(self, "No Changes", "All sources agree — no changes needed.")
            self._go_to_launch()
            return
        self._scraping.set_status(f"Done — {len(changes)} change(s) to review.")
        if self._dry_run:
            lines = [
                f"{len(changes)} proposed ownership change(s) found:\n",
                f"{'Pick':<8} {'Rnd':<5} {'Current Owner':<18} {'New Owner':<18}",
                "─" * 52,
            ]
            for c in changes:
                if "overall" in c:
                    rnd  = c.get("round", "?")
                    curr = c.get("current", {})
                    curr_abbr = curr.get("abbr", "—") if curr else "NEW"
                    curr_team = curr.get("team", "(new slot)") if curr else "(new slot)"
                    prop = c["proposed"]
                    lines.append(
                        f"#{c['overall']:<7} R{rnd:<4} "
                        f"{curr_abbr} ({curr_team[:12]:<12})  →  "
                        f"{prop['abbr']} ({prop['team'][:12]})"
                    )
                else:
                    action = c["action"].upper()
                    year   = c.get("year", "?")
                    rnd    = c.get("round", "?")
                    orig   = c.get("original_abbr", "?")
                    curr   = c.get("current_abbr", "?")
                    lines.append(f"{action}  {year} R{rnd}  orig={orig}  current={curr}")
            QMessageBox.information(self, "Preview — No files written", "\n".join(lines))
            self._go_to_launch()
            return
        self._review.load_changes(changes, ai, self._mode)
        self._stack.setCurrentIndex(REVIEW)
        self.resize(540, 480)

    def _on_worker_error(self, message: str):
        QMessageBox.critical(self, "Error", message)
        self._go_to_launch()

    def _on_review_complete(self, accepted: list):
        if not accepted:
            QMessageBox.information(self, "Done", "No changes accepted.")
            self._go_to_launch()
            return
        try:
            self._apply_and_write(accepted)
        except Exception as e:
            QMessageBox.critical(self, "Write Error", str(e))
            self._go_to_launch()
            return
        reply = QMessageBox.question(
            self, "Upload to Bluehost",
            f"{len(accepted)} change(s) written. Upload to Bluehost now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._upload()
        self._go_to_launch()

    def _apply_and_write(self, accepted: list):
        from fetch_draft_picks.deployer import archive_json
        from fetch_draft_picks.differ   import _future_key
        date_str = datetime.now().strftime("%Y-%m-%d")
        now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if self._mode in ("current", "both"):
            with open(CURRENT_JSON) as f:
                data = json.load(f)
            archive_json(CURRENT_JSON, ARCHIVE_DIR, date_str)
            idx = {p["overall"]: p for p in data["picks"]}
            for c in [x for x in accepted if "overall" in x]:
                if c.get("current") is None:
                    idx[c["overall"]] = c["proposed"]
                else:
                    idx[c["overall"]].update(c["proposed"])
            data["picks"]        = [idx[k] for k in sorted(idx)]
            data["generated_at"] = now_str
            with open(CURRENT_JSON, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        if self._mode in ("future", "both"):
            with open(FUTURE_JSON) as f:
                data = json.load(f)
            archive_json(FUTURE_JSON, ARCHIVE_DIR, date_str)
            idx = {_future_key(p): p for p in data["traded_picks"]}
            for c in [x for x in accepted if "action" in x]:
                key = (c.get("year"), c.get("round"), c.get("original_abbr"))
                if c["action"] == "add":
                    idx[key] = {k: c[k] for k in ("year", "round", "original_abbr", "current_abbr")}
                elif c["action"] == "update":
                    idx[key]["current_abbr"] = c["current_abbr"]["proposed"]
                elif c["action"] == "remove":
                    idx.pop(key, None)
            data["traded_picks"] = list(idx.values())
            data["generated_at"] = now_str
            with open(FUTURE_JSON, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def _upload(self):
        from fetch_draft_picks.deployer import upload_files
        paths = []
        if self._mode in ("current", "both"):
            paths.append(str(CURRENT_JSON))
        if self._mode in ("future", "both"):
            paths.append(str(FUTURE_JSON))
        results  = upload_files(paths)
        failures = [r for r in results if not r["success"]]
        if failures:
            QMessageBox.warning(self, "Upload Failures",
                "\n".join(f"{r['path']}: {r['error']}" for r in failures))
        else:
            QMessageBox.information(self, "Upload Complete", "All files uploaded successfully.")

    def _go_to_launch(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)
        self._stack.setCurrentIndex(LAUNCH)
        self.resize(460, 380)
