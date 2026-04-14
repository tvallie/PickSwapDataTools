"""app.py — QApplication entry point."""
import os
import re
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow


def _load_api_key():
    """Pull ANTHROPIC_API_KEY from ~/.zshrc if not already in environment."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    zshrc = Path.home() / ".zshrc"
    if not zshrc.exists():
        return
    for line in zshrc.read_text().splitlines():
        m = re.match(r'export\s+ANTHROPIC_API_KEY=["\']?([^"\']+)["\']?', line.strip())
        if m:
            os.environ["ANTHROPIC_API_KEY"] = m.group(1)
            return


def main():
    _load_api_key()
    app = QApplication(sys.argv)
    app.setApplicationName("NFL Draft Pick Updater")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
