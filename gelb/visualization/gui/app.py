"""
QApplication bootstrap for gelb-view GUI.
"""

import matplotlib
matplotlib.use('QtAgg')  # Must be set before any pyplot import

import signal
import sys
from PySide6.QtWidgets import QApplication
from gelb.visualization.gui.main_window import GeLBViewMainWindow


def launch_gui(files=None):
    """Create QApplication, show main window, and enter the event loop.

    Parameters
    ----------
    files : list[str] | None
        NetCDF file paths to open on startup.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    # Qt's event loop does not return to Python, so Python's own SIGINT
    # handler never runs and Ctrl-C in the terminal that started the
    # viewer (``gelb-run --view``, the VS Code Run view's Stop) would be
    # ignored.  The default action ends the process instead.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    window = GeLBViewMainWindow()

    for path in (files or []):
        window.open_file(path)

    window.show()
    sys.exit(app.exec())
