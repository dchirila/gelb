"""
QAction definitions for menus and context menus.
"""

from PySide6.QtGui import QAction, QKeySequence


def create_open_action(parent, callback):
    """Create File > Open action."""
    action = QAction('&Open...', parent)
    action.setShortcut(QKeySequence.StandardKey.Open)
    action.setStatusTip('Open a NetCDF file')
    action.triggered.connect(callback)
    return action


def create_close_action(parent, callback):
    """Create File > Close action."""
    action = QAction('&Close', parent)
    action.setShortcut(QKeySequence.StandardKey.Close)
    action.setStatusTip('Close the selected source file')
    action.triggered.connect(callback)
    return action


def create_quit_action(parent, callback):
    """Create File > Quit action."""
    action = QAction('&Quit', parent)
    action.setShortcut(QKeySequence.StandardKey.Quit)
    action.setStatusTip('Exit gelb-view')
    action.triggered.connect(callback)
    return action
