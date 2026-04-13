"""scraping.py — Panel 1: live source grid + collapsible log."""
import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QTextEdit, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCursor
from gui.styles import GREEN, AMBER, RED, FG_DIM

_STATUS_ICON  = {"ok": "✓", "error": "✗", "waiting": "⏳"}
_STATUS_COLOR = {"ok": GREEN, "error": RED, "waiting": FG_DIM}


class ScrapingPanel(QWidget):
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row_map: dict[str, int] = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        self._status_label = QLabel("Scraping sources…")
        header.addWidget(self._status_label)
        header.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.cancel_requested)
        header.addWidget(cancel_btn)
        root.addLayout(header)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Source", "Method", "Time", ""])
        self._table.setColumnWidth(0, 180)
        self._table.setColumnWidth(1, 100)
        self._table.setColumnWidth(2, 70)
        self._table.setColumnWidth(3, 30)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root.addWidget(self._table)

        log_toggle = QPushButton("▶ Log")
        log_toggle.setCheckable(True)
        log_toggle.setFixedWidth(80)
        log_toggle.toggled.connect(self._toggle_log)
        root.addWidget(log_toggle)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(160)
        self._log.setVisible(False)
        root.addWidget(self._log)

        root.addStretch()

    def _toggle_log(self, checked: bool):
        self._log.setVisible(checked)

    def reset(self, source_names: list[str]):
        self._row_map = {}
        self._table.setRowCount(len(source_names))
        for i, name in enumerate(source_names):
            self._set_row(i, name, "—", "—", "waiting")
            self._row_map[name] = i
        self._table.resizeRowsToContents()
        self._log.clear()
        self._status_label.setText("Scraping sources…")

    def _set_row(self, row: int, name: str, method: str, elapsed: str, status: str):
        color = QColor(_STATUS_COLOR.get(status, FG_DIM))
        icon_item = QTableWidgetItem(_STATUS_ICON.get(status, "?"))
        icon_item.setForeground(color)
        icon_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 0, QTableWidgetItem(name))
        self._table.setItem(row, 1, QTableWidgetItem(method))
        self._table.setItem(row, 2, QTableWidgetItem(elapsed))
        self._table.setItem(row, 3, icon_item)

    def on_source_updated(self, name: str, method: str, elapsed: float, status: str):
        row = self._row_map.get(name)
        if row is not None:
            self._set_row(row, name, method, f"{elapsed:.1f}s", status)

    def on_log_message(self, level: str, text: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._log.append(f"{ts}  {level:<5}  {text}")
        self._log.moveCursor(QTextCursor.MoveOperation.End)

    def set_status(self, text: str):
        self._status_label.setText(text)
