"""A composite plot keeps the chosen colormap across time steps.

The *cmap* box of the Magnitude, Vorticity and Side-by-Side plots applies
to every frame: a time step or an animation tick redraws with the chosen
map, not with a built-in one. Vorticity starts from a diverging map
(``RdBu_r``), the others from ``viridis`` (user manual, chapter 2,
"Viewing results"). Runs offscreen in a subprocess, like the other
gelb-view tests.
"""
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

pytest.importorskip('PySide6')
netCDF4 = pytest.importorskip('netCDF4')


@pytest.mark.parametrize(('plot_type', 'initial'), [
    ('Vorticity', 'RdBu_r'), ('Magnitude', 'viridis'), ('Side-by-Side', 'viridis')])
def test_composite_plot_keeps_the_chosen_colormap(tmp_path, plot_type, initial):
    path = tmp_path / 'data.nc'
    rng = np.random.default_rng(0)
    with netCDF4.Dataset(path, 'w') as ds:
        ds.createDimension('time', None)
        ds.createVariable('time', 'i4', ('time',))[:] = [0, 1, 2]
        for dim in ['x', 'y']:
            ds.createDimension(dim, 6)
            ds.createVariable(dim, 'i4', (dim,))[:] = list(range(6))
        for name in ['ux', 'uy']:
            ds.createVariable(name, 'f8', ('time', 'y', 'x'))[:] = rng.random((3, 6, 6))
    script = '''
import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from gelb.visualization.data_viewer import GeLBDataset
from gelb.visualization.gui.composite_plot_panel import CompositePlotDockWidget
path, plot_type, initial = sys.argv[1:4]
app = QApplication([])
dataset = GeLBDataset(path)
window = QMainWindow()
panel = CompositePlotDockWidget(path, dataset, ['ux', 'uy'], plot_type, 0)
window.setCentralWidget(panel)
window.show()
def cmaps():
    panel._canvas.draw()
    return sorted({im.get_cmap().name for im in panel._images if im is not None})
assert panel._cmap_selector.value() == initial, panel._cmap_selector.value()
assert cmaps() == [initial], cmaps()
panel._cmap_selector.set_value('jet')
assert cmaps() == ['jet'], cmaps()
panel._anim_controls._advance()          # an animation tick
assert cmaps() == ['jet'], ('tick', cmaps())
panel._anim_controls.frame_tick.emit(2)  # a time-step change
assert cmaps() == ['jet'], ('step', cmaps())
panel.close()
dataset.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(path), plot_type, initial],
                            env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
