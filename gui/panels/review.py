"""review.py — Panel 2: grid-based change approval with checkboxes."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor
from gui.styles import GREEN, RED, AMBER


class ReviewPanel(QWidget):
    review_complete = pyqtSignal(list)
    quit_review     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._changes: list[dict] = []
        self._mode = "current"
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        self._title = QLabel("Review Changes")
        self._title.setObjectName("title_label")
        header.addWidget(self._title)
        header.addStretch()
        self._counter = QLabel("")
        self._counter.setObjectName("counter_label")
        header.addWidget(self._counter)
        root.addLayout(header)

        self._lbl = QLabel("")
        root.addWidget(self._lbl)

        self._table = QTableWidget()
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setShowGrid(True)
        root.addWidget(self._table)

        btn_row = QHBoxLayout()
        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setFixedWidth(90)
        self._select_all_btn.clicked.connect(self._select_all)
        self._select_none_btn = QPushButton("Select None")
        self._select_none_btn.setFixedWidth(90)
        self._select_none_btn.clicked.connect(self._select_none)
        btn_row.addWidget(self._select_all_btn)
        btn_row.addWidget(self._select_none_btn)
        btn_row.addStretch()
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("quit_btn")
        self._cancel_btn.setFixedWidth(80)
        self._cancel_btn.clicked.connect(self.quit_review)
        self._apply_btn = QPushButton("Apply Selected")
        self._apply_btn.setObjectName("run_btn")
        self._apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._apply_btn)
        root.addLayout(btn_row)

    def load_changes(self, changes: list[dict], ai: dict, mode: str):
        self._changes = list(changes)
        self._mode    = mode
        self._build_table(changes, ai, mode)

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
        hdr.setSectionResizeMode(len(headers) - 1, QHeaderView.ResizeMode.Stretch)

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

    def _build_table(self, changes: list, ai: dict, mode: str):
        is_future = mode == "future"

        sources = []
        for c in changes:
            for s in c.get("_source_verdicts", {}):
                if s not in sources:
                    sources.append(s)

        if is_future:
            fixed = ["", "Action", "Year", "Rnd", "Original", "Your JSON", "Proposed"]
        else:
            fixed = ["", "Pick", "Rnd", "Your JSON", "Proposed Team"]

        all_headers = fixed + sources
        self._table.setColumnCount(len(all_headers))
        self._table.setRowCount(len(changes))
        self._table.setHorizontalHeaderLabels(all_headers)

        hdr = self._table.horizontalHeader()
        proposed_col = 6 if is_future else 4
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(0, 40)
        for col in range(1, len(all_headers)):
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

        def checkbox(checked=True):
            item = QTableWidgetItem()
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            return item

        for row, c in enumerate(changes):
            verdicts = c.get("_source_verdicts", {})
            self._table.setItem(row, 0, checkbox(checked=False))

            if is_future:
                action       = c["action"].upper()
                year         = c.get("year", "?")
                rnd          = c.get("round", "?")
                orig         = c.get("original_abbr", "?")
                proposed_val = c.get("_proposed_curr")

                if c["action"] == "add":
                    json_val     = "not tracked"
                    proposed_str = c.get("current_abbr", "?")
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
                self._table.setItem(row, 1, cell(action, color=action_color))
                self._table.setItem(row, 2, cell(str(year)))
                self._table.setItem(row, 3, cell(f"R{rnd}"))
                self._table.setItem(row, 4, cell(orig))
                self._table.setItem(row, 5, cell(json_val))
                self._table.setItem(row, 6, cell(proposed_str, align=left))

                for off, src in enumerate(sources):
                    abbr   = verdicts.get(src)
                    agrees = (abbr == proposed_val) if proposed_val else False
                    icon   = "✓" if agrees else ("✗" if abbr else "—")
                    text   = f"{icon}  {abbr}" if abbr else "—"
                    self._table.setItem(row, len(fixed) + off,
                                        cell(text, color=GREEN if agrees else (RED if abbr else None)))
            else:
                prop         = c["proposed"]
                json_abbr    = c.get("_json_abbr", "—")
                proposed_val = prop["abbr"]

                self._table.setItem(row, 1, cell(f"#{c['overall']}"))
                self._table.setItem(row, 2, cell(f"R{c.get('round', '?')}"))
                self._table.setItem(row, 3, cell(json_abbr))
                self._table.setItem(row, 4, cell(f"{prop['abbr']}  —  {prop['team']}", align=left))

                for off, src in enumerate(sources):
                    abbr   = verdicts.get(src)
                    agrees = abbr == proposed_val
                    icon   = "✓" if agrees else "✗"
                    text   = f"{icon}  {abbr}" if abbr else "—"
                    self._table.setItem(row, len(fixed) + off,
                                        cell(text, color=GREEN if agrees else RED))

        self._table.resizeRowsToContents()
        self._table.setMinimumHeight(min(500, 60 + len(changes) * 28))
        self._lbl.setText(f"{len(changes)} proposed change(s) — check the ones to apply:")
        self._counter.setText(f"{len(changes)} change(s)")

    def _select_all(self):
        for row in range(self._table.rowCount()):
            self._table.item(row, 0).setCheckState(Qt.CheckState.Checked)

    def _select_none(self):
        for row in range(self._table.rowCount()):
            self._table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)

    def _on_apply(self):
        accepted = [
            self._changes[row]
            for row in range(self._table.rowCount())
            if self._table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
        if not accepted:
            QMessageBox.information(self, "Nothing Selected", "No changes selected — nothing will be written.")
            return
        self.review_complete.emit(accepted)
