"""Bundled SVG icon access for source and PyInstaller builds."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QAbstractButton

ICON_SIZE = QSize(18, 18)


def asset_path(relative_path: str) -> Path:
    """Return an asset path in a source checkout or frozen application."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "assets" / relative_path
    return Path(__file__).resolve().parents[2] / "assets" / relative_path


def svg_icon(name: str) -> QIcon:
    """Load a named icon from the bundled SVG set."""
    return QIcon(str(asset_path(f"icons/{name}.svg")))


def apply_icon(button: QAbstractButton, name: str) -> None:
    """Apply a consistent SVG icon and spacing to a button."""
    button.setIcon(svg_icon(name))
    button.setIconSize(ICON_SIZE)


def logo_icon() -> QIcon:
    """Return the EchoScribe document-and-wave brand mark."""
    return QIcon(str(asset_path("logo.svg")))
