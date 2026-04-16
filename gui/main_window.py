"""main_window.py — QMainWindow with QStackedWidget panel management."""
import json
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QStackedWidget, QMessageBox,
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from gui.panels.launch   import LaunchPanel
from gui.panels.scraping import ScrapingPanel
from gui.panels.review   import ReviewPanel
from gui.worker          import ScraperWorker
from gui.styles          import STYLESHEET, GREEN, RED, AMBER
from fetch_draft_picks.scraper import CURRENT_SOURCES, FUTURE_SOURCES

JSON_DIR     = Path("/Users/todd/CodingProjects/PickSwapWeb/json")
CURRENT_JSON = JSON_DIR / "draft_order_current.json"
FUTURE_JSON  = JSON_DIR / "future_pick_trades.json"
ARCHIVE_DIR  = JSON_DIR / "archive"
CURRENT_HISTORY = JSON_DIR / "current_pick_history.json"
FUTURE_HISTORY  = JSON_DIR / "future_pick_history.json"

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
        self._launch.history_requested.connect(self._on_history)
        self._scraping.cancel_requested.connect(self._on_cancel)
        self._review.review_complete.connect(self._on_review_complete)
        self._review.quit_review.connect(self._go_to_launch)

        self._stack.setCurrentIndex(LAUNCH)

    def _on_run(self, mode: str, dry_run: bool):
        self._mode    = mode
        self._dry_run = dry_run

        if mode == "current":
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
        if self._worker and self._worker.pdf_errors:
            errs = "\n".join(self._worker.pdf_errors)
            QMessageBox.warning(self, "PDF Import Failed",
                f"One or more PDF sources failed to parse and were excluded from the comparison:\n\n{errs}")
        if not changes:
            QMessageBox.information(self, "No Changes", "Scraped data matches your JSON — no changes needed.")
            self._go_to_launch()
            return
        self._scraping.set_status(f"Done — {len(changes)} change(s) to review.")
        if self._dry_run:
            self._show_dry_run_dialog(changes)
            self._go_to_launch()
            return
        self._review.load_changes(changes, ai, self._mode)
        self._stack.setCurrentIndex(REVIEW)
        self.resize(800, 560)

    def _show_dry_run_dialog(self, changes: list):
        # Detect mode from change structure
        is_future = changes and "action" in changes[0]

        # Collect source names in stable order
        sources = []
        for c in changes:
            for s in c.get("_source_verdicts", {}):
                if s not in sources:
                    sources.append(s)

        if is_future:
            fixed_headers = ["Action", "Year", "Rnd", "Original Team", "Your JSON", "Proposed"]
        else:
            fixed_headers = ["Pick", "Rnd", "Your JSON", "Proposed Team"]
        all_headers = fixed_headers + sources

        dlg = QDialog(self)
        dlg.setWindowTitle("Preview — No files written")
        dlg.setStyleSheet(self.styleSheet())

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        lbl = QLabel(f"{len(changes)} proposed {'future pick' if is_future else 'ownership'} change(s)")
        lbl.setObjectName("title_label")
        layout.addWidget(lbl)

        tbl = QTableWidget(len(changes), len(all_headers))
        tbl.setHorizontalHeaderLabels(all_headers)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setShowGrid(True)

        hdr = tbl.horizontalHeader()
        proposed_col = 5 if is_future else 3
        for col in range(len(all_headers)):
            if col == proposed_col:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
            else:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        left = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft

        def cell(text, align=Qt.AlignmentFlag.AlignCenter, color=None):
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(align)
            if color:
                item.setForeground(QColor(color))
            return item

        for row, c in enumerate(changes):
            verdicts     = c.get("_source_verdicts", {})
            proposed_val = None

            if is_future:
                action = c["action"].upper()
                year   = c.get("year", "?")
                rnd    = c.get("round", "?")
                orig   = c.get("original_abbr", "?")

                if c["action"] == "add":
                    json_val     = "not tracked"
                    proposed_str = c.get("current_abbr", "?")
                    proposed_val = c.get("_proposed_curr") or proposed_str
                elif c["action"] == "update":
                    ca           = c["current_abbr"]
                    json_val     = ca.get("current", "?")
                    proposed_str = ca.get("proposed", "?")
                    proposed_val = proposed_str
                else:
                    json_val     = c.get("current_abbr", "?")
                    proposed_str = "— remove —"
                    proposed_val = None

                action_color = {"ADD": GREEN, "UPDATE": AMBER, "REMOVE": RED}.get(action)
                tbl.setItem(row, 0, cell(action, color=action_color))
                tbl.setItem(row, 1, cell(str(year)))
                tbl.setItem(row, 2, cell(f"R{rnd}"))
                tbl.setItem(row, 3, cell(orig))
                tbl.setItem(row, 4, cell(json_val))
                tbl.setItem(row, 5, cell(proposed_str, align=left))

                for col_offset, src in enumerate(sources):
                    abbr   = verdicts.get(src)
                    agrees = (abbr == proposed_val) if proposed_val else False
                    icon   = "✓" if agrees else ("✗" if abbr else "—")
                    text   = f"{icon}  {abbr}" if abbr else "—"
                    tbl.setItem(row, len(fixed_headers) + col_offset,
                                cell(text, color=GREEN if agrees else (RED if abbr else None)))
            else:
                prop         = c["proposed"]
                json_abbr    = c.get("_json_abbr", "—")
                proposed_val = prop["abbr"]

                tbl.setItem(row, 0, cell(f"#{c['overall']}"))
                tbl.setItem(row, 1, cell(f"R{c.get('round', '?')}"))
                tbl.setItem(row, 2, cell(json_abbr))
                tbl.setItem(row, 3, cell(f"{prop['abbr']}  —  {prop['team']}", align=left))

                for col_offset, src in enumerate(sources):
                    abbr   = verdicts.get(src)
                    agrees = abbr == proposed_val
                    icon   = "✓" if agrees else "✗"
                    text   = f"{icon}  {abbr}" if abbr else "—"
                    tbl.setItem(row, len(fixed_headers) + col_offset,
                                cell(text, color=GREEN if agrees else RED))

        tbl.resizeRowsToContents()
        tbl.setMinimumHeight(min(500, 60 + len(changes) * 28))
        layout.addWidget(tbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        dlg.adjustSize()
        dlg.exec()

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
        from fetch_draft_picks.deployer      import archive_json
        from fetch_draft_picks.differ        import _future_key
        from fetch_draft_picks.pdf_importer  import archive_processed_pdfs
        from fetch_draft_picks.historian     import append_current_history, append_future_history
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
            append_current_history(
                [x for x in accepted if "overall" in x],
                date_str,
                CURRENT_HISTORY,
            )
            if self._worker:
                archive_processed_pdfs(self._worker.pdf_results.get("current", []), date_str)

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
            append_future_history(
                [x for x in accepted if "action" in x],
                date_str,
                FUTURE_HISTORY,
            )
            if self._worker:
                archive_processed_pdfs(self._worker.pdf_results.get("future", []), date_str)

    def _on_history(self, want_current: bool, want_future: bool):
        self._stack.setCurrentIndex(SCRAPING)
        self._scraping.set_status("Scraping pick history from prosportstransactions.com…")
        self._run_history(want_current, want_future)

    def _run_history(self, want_current: bool, want_future: bool):
        from fetch_draft_picks.scraper   import scrape_all_sources, CURRENT_HISTORY_SOURCES, FUTURE_HISTORY_SOURCES
        from fetch_draft_picks.differ    import diff_current_history, diff_future_history

        new_entries: list[dict] = []

        if want_current:
            results  = scrape_all_sources(CURRENT_HISTORY_SOURCES)
            scraped  = [p for r in results if r["picks"] for p in r["picks"]]
            existing = json.loads(CURRENT_HISTORY.read_text()).get("history", []) if CURRENT_HISTORY.exists() else []
            new_entries += diff_current_history(scraped, existing)

        if want_future:
            results  = scrape_all_sources(FUTURE_HISTORY_SOURCES)
            scraped  = [p for r in results if r["picks"] for p in r["picks"]]
            existing = json.loads(FUTURE_HISTORY.read_text()).get("history", []) if FUTURE_HISTORY.exists() else []
            new_entries += diff_future_history(scraped, existing)

        if not new_entries:
            QMessageBox.information(self, "No New Entries", "No new history entries found.")
            self._stack.setCurrentIndex(LAUNCH)
            return

        if want_current and want_future:
            mode = "both"
        elif want_current:
            mode = "current"
        else:
            mode = "future"

        # Swap the review_complete handler so history entries are processed correctly
        self._review.review_complete.disconnect(self._on_review_complete)
        self._review.review_complete.connect(self._on_history_applied)

        self._review.load_history(new_entries, mode)
        self._stack.setCurrentIndex(REVIEW)
        self.resize(900, 600)

    def _on_history_applied(self, accepted: list):
        from fetch_draft_picks.historian import append_current_history, append_future_history
        date_str = datetime.now().strftime("%Y-%m-%d")

        current_accepted = [e for e in accepted if "overall" in e]
        future_accepted  = [e for e in accepted if "year"   in e and "overall" not in e]

        if current_accepted:
            append_current_history(current_accepted, date_str, CURRENT_HISTORY)
        if future_accepted:
            append_future_history(future_accepted, date_str, FUTURE_HISTORY)

        # Restore the normal review_complete handler
        self._review.review_complete.disconnect(self._on_history_applied)
        self._review.review_complete.connect(self._on_review_complete)

        self._go_to_launch()

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
