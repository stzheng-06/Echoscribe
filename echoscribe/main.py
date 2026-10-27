"""Main application entry point for EchoScribe."""
import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.icons import logo_icon


def setup_logging() -> None:
    import os

    app_data = os.environ.get("APPDATA", "")
    log_dir = Path(app_data) / "EchoScribe" / "logs" if app_data else Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "echoscribe.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setWindowIcon(logo_icon())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
