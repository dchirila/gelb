"""The *Sources* tree offers each variable only the plots that can open.

A 3D variable has no "New Cross-Section" entry, and a selection of 3D
variables gets no composite plots: those panels draw 1D or 2D arrays, so
on 3D data they opened no plot and printed a traceback. 3D data is viewed
through the heatmap and the animation, one slice at a time, and the menu
says so with a disabled "Use ParaView for 3D visualizations" entry (user
manual, *Getting started*, gelb-view). Runs offscreen in a subprocess,
like the other gelb-view tests.
"""
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip('PySide6')
netCDF4 = pytest.importorskip('netCDF4')

HINT = 'Use ParaView for 3D visualizations'   # a disabled entry
SINGLE = {1: ['New Heatmap', 'New Line Plot', 'New Animation'],
          2: ['New Heatmap', 'New Cross-Section', 'New Animation'],
          3: ['New Heatmap', 'New Animation', '', HINT]}   # '' = separator
COMPOSITE = {1: ['Side-by-Side (2 vars)', 'Magnitude'],
             2: ['Side-by-Side (2 vars)', 'Vector Field', 'Streamlines',
                 'Magnitude', 'Vorticity', 'Particle Animation'],
             3: [HINT]}


@pytest.mark.parametrize(('ndim', 'select', 'expected'), [
    (ndim, select, menus[ndim])
    for select, menus in [(1, SINGLE), (2, COMPOSITE)] for ndim in [1, 2, 3]])
def test_variable_context_menu(tmp_path, ndim, select, expected):
    path = tmp_path / 'data.nc'
    dims = ['x', 'y', 'z'][:ndim]
    with netCDF4.Dataset(path, 'w') as ds:
        ds.createDimension('time', None)
        ds.createVariable('time', 'i4', ('time',))[:] = [0, 1]
        for dim in dims:
            ds.createDimension(dim, 4)
            ds.createVariable(dim, 'i4', (dim,))[:] = list(range(4))
        for name in ['first', 'second']:
            ds.createVariable(name, 'f8', ('time', *dims))[:] = 1.0
    # The menu runs its own event loop until it closes; a timer inside
    # that loop records the entries and closes it.
    script = '''
import sys
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMenu
from gelb.visualization.gui.main_window import GeLBViewMainWindow
app = QApplication([])
menus = []
def grab():
    shown = [w for w in app.topLevelWidgets() if isinstance(w, QMenu) and w.isVisible()]
    if not shown:
        QTimer.singleShot(10, grab)
        return
    menus.append([a.text() for a in shown[0].actions()])
    assert all(a.isEnabled() == ('ParaView' not in a.text()) for a in shown[0].actions())
    shown[0].close()
window = GeLBViewMainWindow()
window.open_file(sys.argv[1])
tree = window._source_tree
tree.expandAll()
tree.clearSelection()
for name in ['first', 'second'][:int(sys.argv[2])]:
    tree._find_variable_item(sys.argv[1], name).setSelected(True)
QTimer.singleShot(0, grab)
tree._on_context_menu(tree.visualItemRect(tree._find_variable_item(sys.argv[1], 'first')).center())
assert menus == [sys.argv[3].split(',')], menus
window.close_file(sys.argv[1])
window.close()
'''
    result = subprocess.run(
        [sys.executable, '-c', script, str(path), str(select), ','.join(expected)],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
