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
