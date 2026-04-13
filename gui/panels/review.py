"""review.py — Panel 2: one change at a time approval UI."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QSpacerItem, QSizePolicy, QMessageBox,
)
from PyQt6.QtCore import pyqtSignal, Qt


class ReviewPanel(QWidget):
    review_complete = pyqtSignal(list)
    quit_review     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._changes: list[dict] = []
        self._ai: dict = {}
        self._mode = "current"
        self._idx = 0
        self._accepted: list[dict] = []
        self._rejected: list[dict] = []
        self._skipped:  list[dict] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(16)

        header = QHBoxLayout()
        self._title = QLabel("Review Changes")
        self._title.setObjectName("title_label")
        header.addWidget(self._title)
        header.addStretch()
        self._counter = QLabel("")
        self._counter.setObjectName("counter_label")
        header.addWidget(self._counter)
        root.addLayout(header)

        self._card = QFrame()
        self._card.setObjectName("change_card")
        self._card.setContentsMargins(12, 12, 12, 12)
        card_layout = QVBoxLayout(self._card)
        card_layout.setSpacing(8)
        self._pick_label     = QLabel()
        self._pick_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        self._current_label  = QLabel()
        self._proposed_label = QLabel()
        self._proposed_label.setStyleSheet("font-weight: bold;")
        for w in [self._pick_label, self._current_label, self._proposed_label]:
            card_layout.addWidget(w)
        root.addWidget(self._card)

        self._ai_frame  = QFrame()
        ai_layout = QVBoxLayout(self._ai_frame)
        ai_layout.setContentsMargins(0, 0, 0, 0)
        self._ai_header = QLabel("AI Analysis")
        self._ai_header.setObjectName("ai_label")
        self._ai_text   = QLabel()
        self._ai_text.setWordWrap(True)
        ai_layout.addWidget(self._ai_header)
        ai_layout.addWidget(self._ai_text)
        self._ai_frame.setVisible(False)
        root.addWidget(self._ai_frame)

        root.addStretch()

        btn_row = QHBoxLayout()
        self._accept_btn = QPushButton("Accept")
        self._accept_btn.setObjectName("accept_btn")
        self._accept_btn.clicked.connect(self._on_accept)
        self._reject_btn = QPushButton("Reject")
        self._reject_btn.setObjectName("reject_btn")
        self._reject_btn.clicked.connect(self._on_reject)
        self._skip_btn = QPushButton("Skip")
        self._skip_btn.clicked.connect(self._on_skip)
        self._quit_btn = QPushButton("Quit")
        self._quit_btn.setObjectName("quit_btn")
        self._quit_btn.clicked.connect(self._on_quit)
        btn_row.addWidget(self._accept_btn)
        btn_row.addWidget(self._reject_btn)
        btn_row.addWidget(self._skip_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._quit_btn)
        root.addLayout(btn_row)

    def load_changes(self, changes: list[dict], ai: dict, mode: str):
        self._changes  = list(changes)
        self._ai       = ai
        self._mode     = mode
        self._idx      = 0
        self._accepted = []
        self._rejected = []
        self._skipped  = []
        self._show_current()

    def _show_current(self):
        if self._idx >= len(self._changes):
            self._finish()
            return
        change = self._changes[self._idx]
        self._counter.setText(f"{self._idx + 1} of {len(self._changes)}")
        if self._mode == "current":
            self._render_current(change)
        else:
            self._render_future(change)
        key     = self._ai_key(change)
        ai_data = self._ai.get(key)
        if ai_data:
            self._ai_header.setText(f"AI Analysis  ({ai_data.get('confidence', '?')} confidence)")
            self._ai_text.setText(ai_data.get("summary", ""))
            self._ai_frame.setVisible(True)
        else:
            self._ai_frame.setVisible(False)

    def _render_current(self, change: dict):
        overall = change["overall"]
        self._pick_label.setText(
            f"Pick #{overall}  —  Round {change.get('round', '?')}, Pick {change.get('pick_in_round', '?')}"
        )
        curr = change.get("current")
        prop = change["proposed"]
        self._current_label.setText(
            f"Current:    {curr['team']}  ({curr['abbr']})" if curr else "Current:    (new pick slot)"
        )
        orig = prop.get("original_team", "")
        orig_str = f"   (orig: {orig})" if orig and orig != prop["team"] else ""
        self._proposed_label.setText(f"Proposed:  {prop['team']}  ({prop['abbr']}){orig_str}")

    def _render_future(self, change: dict):
        action = change["action"]
        year   = change.get("year", "?")
        round_ = change.get("round", "?")
        orig   = change.get("original_abbr", "?")
        self._pick_label.setText(f"{action.upper()}  —  {year} Round {round_}")
        if action == "add":
            self._current_label.setText("Current:    (not in database)")
            self._proposed_label.setText(f"Proposed:  {orig} → {change.get('current_abbr', '?')}")
        elif action == "update":
            c = change["current_abbr"]
            self._current_label.setText(f"Current:    {orig} → {c['current']}")
            self._proposed_label.setText(f"Proposed:  {orig} → {c['proposed']}")
        elif action == "remove":
            self._current_label.setText(f"Current:    {orig} → {change.get('current_abbr', '?')}")
            self._proposed_label.setText("Proposed:  (remove from database)")

    def _ai_key(self, change: dict) -> str:
        if self._mode == "current":
            return str(change.get("overall", ""))
        return f"{change.get('year')}_{change.get('round')}_{change.get('original_abbr')}"

    def _on_accept(self):
        self._accepted.append(self._changes[self._idx])
        self._advance()

    def _on_reject(self):
        self._rejected.append(self._changes[self._idx])
        self._advance()

    def _on_skip(self):
        self._skipped.append(self._changes[self._idx])
        self._advance()

    def _on_quit(self):
        self.quit_review.emit()

    def _advance(self):
        self._idx += 1
        if self._idx >= len(self._changes):
            if self._skipped:
                reply = QMessageBox.question(
                    self, "Skipped Items",
                    f"{len(self._skipped)} item(s) skipped. Review them now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._changes = self._skipped
                    self._skipped = []
                    self._idx     = 0
                    self._show_current()
                    return
            self._finish()
        else:
            self._show_current()

    def _finish(self):
        QMessageBox.information(
            self, "Review Complete",
            f"Accepted: {len(self._accepted)}  |  Rejected: {len(self._rejected)}"
        )
        self.review_complete.emit(self._accepted)
