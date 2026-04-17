from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.bootstrap import build_main_window


def main() -> int:
    app = QApplication(sys.argv)
    window = build_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

