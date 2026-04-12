"""styles.py — Qt stylesheet and color constants."""

BG        = "#1e1e2e"
BG_CARD   = "#2a2a3e"
BG_INPUT  = "#313145"
FG        = "#cdd6f4"
FG_DIM    = "#6c7086"
ACCENT    = "#89b4fa"
GREEN     = "#a6e3a1"
AMBER     = "#f9e2af"
RED       = "#f38ba8"
BORDER    = "#45475a"

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {FG};
    font-family: "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}
QPushButton {{
    background-color: {BG_INPUT};
    color: {FG};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 18px;
    min-width: 80px;
}}
QPushButton:hover {{
    background-color: {ACCENT};
    color: {BG};
    border: 1px solid {ACCENT};
}}
QPushButton#run_btn {{
    background-color: {ACCENT};
    color: {BG};
    font-weight: bold;
    font-size: 15px;
    padding: 10px 40px;
    border-radius: 8px;
}}
QPushButton#run_btn:hover {{
    background-color: {FG};
}}
QPushButton#quit_btn {{
    background-color: transparent;
    color: {FG_DIM};
    border: none;
    min-width: 40px;
    padding: 4px 8px;
}}
QPushButton#accept_btn {{
    background-color: {GREEN};
    color: {BG};
    font-weight: bold;
}}
QPushButton#reject_btn {{
    background-color: {RED};
    color: {BG};
    font-weight: bold;
}}
QRadioButton, QCheckBox {{
    color: {FG};
    spacing: 8px;
}}
QRadioButton::indicator, QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {BORDER};
    border-radius: 8px;
    background: {BG_INPUT};
}}
QCheckBox::indicator {{
    border-radius: 4px;
}}
QRadioButton::indicator:checked, QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QTableWidget {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    gridline-color: {BORDER};
}}
QTableWidget::item {{
    padding: 4px 8px;
}}
QHeaderView::section {{
    background-color: {BG_INPUT};
    color: {FG_DIM};
    border: none;
    padding: 4px 8px;
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
}}
QTextEdit {{
    background-color: {BG_CARD};
    color: {FG_DIM};
    border: 1px solid {BORDER};
    border-radius: 6px;
    font-family: "SF Mono", "Menlo", monospace;
    font-size: 11px;
    padding: 4px;
}}
QFrame#change_card {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 12px;
}}
QLabel#ai_label {{
    color: {AMBER};
    font-style: italic;
}}
QLabel#counter_label {{
    color: {FG_DIM};
    font-size: 12px;
}}
QLabel#title_label {{
    font-size: 18px;
    font-weight: bold;
    color: {ACCENT};
}}
"""
