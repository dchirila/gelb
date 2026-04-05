"""Open real Qt widgets offscreen, isolated from matplotlib's process state."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip('PySide6')
netCDF4 = pytest.importorskip('netCDF4')


@pytest.mark.parametrize(('ndim', 'records', 'expected'), [
    (1, 2, 'Heatmap'), (1, 1, 'Line Plot'), (2, 2, 'Heatmap'),
    (3, 2, None), (1, 0, None),
])
def test_default_plot(tmp_path, ndim, records, expected):
    path = tmp_path / 'data.nc'
    dims = ['x', 'y', 'z'][:ndim]
    with netCDF4.Dataset(path, 'w') as ds:
        ds.description = 'Default plot test'
        ds.createDimension('time', None)
        ds.createVariable('time', 'i4', ('time',))[:] = list(range(records))
        for dim in dims:
            ds.createDimension(dim, 4)
            ds.createVariable(dim, 'i4', (dim,))[:] = list(range(4))
        for name in ['first', 'second']:
            var = ds.createVariable(name, 'f8', ('time', *dims))
            if records:
                var[:] = 1.0
    script = '''
import sys
from PySide6.QtWidgets import QApplication
from gelb.visualization.gui.main_window import GeLBViewMainWindow
app = QApplication([])
window = GeLBViewMainWindow()
window.open_file(sys.argv[1])
expected = sys.argv[2]
assert window.windowTitle() == 'gelb-view'
assert 'Default plot test' in window._source_tree.topLevelItem(0).text(1)
if expected == 'None':
    assert not window._plot_docks
else:
    [dock] = window._plot_docks.values()
    assert dock._var_name == 'first'
    assert dock._plot_type == expected
    assert dock._im is not None if expected == 'Heatmap' else dock._line is not None
    window.open_file(sys.argv[1])
    assert len(window._plot_docks) == 1
window.close_file(sys.argv[1])
assert not window._datasets and not window._plot_docks
window.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(path), str(expected)],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
