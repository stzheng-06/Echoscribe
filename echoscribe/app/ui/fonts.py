"""Register reliable Windows font fallbacks for Latin and CJK interfaces."""
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

_REGISTERED = False


def register_application_fonts() -> None:
    """Load standard Windows UI fonts when Qt cannot discover them itself."""
    global _REGISTERED
    if _REGISTERED:
        return
    font_dir = Path("C:/Windows/Fonts")
    for filename in ("segoeui.ttf", "segoeuib.ttf", "msyh.ttc", "msyhbd.ttc"):
        path = font_dir / filename
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app = QApplication.instance()
    if app is not None:
        app.setFont(QFont("Segoe UI", 10))
    _REGISTERED = True
