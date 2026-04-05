"""
GUI module for gelb-view (requires PySide6).

This package provides an interactive visualization application built on
Qt (PySide6) with dockable plot panels, a source/variable tree, and menus.
"""

try:
    from PySide6 import QtWidgets  # noqa: F401
    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False
