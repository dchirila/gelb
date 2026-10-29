"""Heatmaps keep one colour bar for the displayed image and one colour range
over all records; line plots keep none.  Time, slice and colormap controls
preserve these invariants.  The range ignores NaN and masked values."""
import os
import subprocess
import sys
import warnings

import pytest

netCDF4 = pytest.importorskip('netCDF4')
np = pytest.importorskip('numpy')

RECORDS = 3

# Every record has its own value range (100 r + cell index, r the record
# index), so a colour range taken from the record or slice on screen would
# differ at every move.  One NaN cell stands for a masked node class.  A
# Qt slot's exception goes to sys.excepthook, so it is collected and fails
# the next check instead of passing unseen; the hook still prints every
# traceback, so a failed check or import shows up in the test's output.
SCRIPT = '''
import sys
errors = []
def collect(kind, value, tb):
    errors.append((kind.__name__, str(value)))
    sys.__excepthook__(kind, value, tb)
sys.excepthook = collect
from PySide6.QtWidgets import QApplication
from gelb.visualization.data_viewer import GeLBDataset
from gelb.visualization.gui.plot_panel import PlotDockWidget

app = QApplication([])
path, plot_type = sys.argv[1], sys.argv[2]
vrange = (float(sys.argv[3]), float(sys.argv[4]))
with GeLBDataset(path) as ds:
    panel = PlotDockWidget(path, ds, 'value', plot_type, 0)
    fig = panel._fig
    heatmap = plot_type in ('Heatmap', 'Animation')

    def check(move):
        panel._canvas.draw()
        assert not errors, (move, errors)
        if heatmap:
            assert set(fig.axes) == {panel._ax, panel._colorbar.ax}, (move, fig.axes)
            assert panel._colorbar.mappable is panel._im, move
            assert panel._im.get_clim() == vrange, (move, panel._im.get_clim(), vrange)
            assert (panel._colorbar.cmap.name == panel._im.get_cmap().name
                    == panel._cmap_selector.value()), move
        else:
            assert fig.axes == [panel._ax], (move, fig.axes)

    check('open')
    time = panel._anim_controls or panel._timestep_slider
    if time is not None:
        for ts in [0, 1, 2, 1]:
            time._slider.setValue(ts)
            check(f'record {ts}')
    if panel._anim_controls is not None:
        for _ in range(4):  # past the last record, back to the first
            panel._anim_controls._advance()
            check('animation tick')
    if panel._slice_controls is not None:
        for axis in ds.spatial_dims:
            panel._slice_controls._axis_combo.setCurrentText(axis)
            check(f'axis {axis}')
            panel._slice_controls._index_spin.setValue(0)
            check(f'axis {axis}, index 0')
    if panel._cmap_selector is not None:
        panel._cmap_selector._combo.setCurrentIndex(1)
        check('colormap')
        if time is not None:
            time._slider.setValue(0)
            check('record 0 after the colormap change')
    panel.close()
'''


@pytest.mark.parametrize(('ndim', 'plot_type'), [
    (3, 'Heatmap'), (3, 'Animation'),
    (2, 'Heatmap'), (2, 'Animation'), (2, 'Cross-Section'),
    (1, 'Heatmap'), (1, 'Animation'), (1, 'Line Plot'),
])
def test_one_colour_bar_and_a_fixed_range(tmp_path, ndim, plot_type):
    pytest.importorskip('PySide6')
    path = tmp_path / 'data.nc'
    sizes = {'x': 5, 'y': 4, 'z': 3}
    dims = ['z', 'y', 'x'][3 - ndim:]
    with netCDF4.Dataset(path, 'w') as ds:
        ds.createDimension('time', None)
        ds.createVariable('time', 'i4', ('time',))[:] = [10 * (r + 1) for r in range(RECORDS)]
        for dim in dims:
            ds.createDimension(dim, sizes[dim])
            ds.createVariable(dim, 'i4', (dim,))[:] = list(range(sizes[dim]))
        shape = [sizes[dim] for dim in dims]
        cells = np.arange(np.prod(shape), dtype=float).reshape(shape)
        values = np.stack([100.0 * r + cells for r in range(RECORDS)])
        values[(1,) + (0,) * ndim] = np.nan
        ds.createVariable('value', 'f8', ('time', *dims))[:] = values
    vrange = [str(np.nanmin(values)), str(np.nanmax(values))]
    result = subprocess.run([sys.executable, '-c', SCRIPT, str(path), plot_type, *vrange],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def _range(path, name='v'):
    from gelb.visualization.data_viewer import GeLBDataset
    with GeLBDataset(path) as ds, warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)  # all-NaN data
        return ds.get_variable_range(name)


@pytest.mark.parametrize('dtype', ['f8', 'f4', 'i8', 'i4'])
@pytest.mark.parametrize('first_dim', ['time', 'y'])
def test_the_range_skips_masked_values(tmp_path, dtype, first_dim):
    path = tmp_path / 'masked.nc'
    values = np.ma.array([[-9, 2, 3], [4, 7, 90]],
                         mask=[[True, False, False], [False, False, True]])
    with netCDF4.Dataset(path, 'w') as ds:
        ds.createDimension(first_dim, 2)
        ds.createDimension('x', 3)
        ds.createVariable('v', dtype, (first_dim, 'x'), fill_value=-99)[:] = values
    assert _range(path) == (2.0, 7.0)


@pytest.mark.parametrize(('records', 'expected'), [
    ([[np.nan, np.nan], [2.0, 7.0]], (2.0, 7.0)),       # an all-NaN record
    ([[np.nan, np.nan], [np.nan, np.nan]], 'nan'),      # all NaN
    ([[-99.0, -99.0], [-99.0, -99.0]], 'nan'),          # all fill values
    ([], ValueError),                                   # no records
])
def test_the_range_of_missing_records(tmp_path, records, expected):
    path = tmp_path / 'missing.nc'
    with netCDF4.Dataset(path, 'w') as ds:
        ds.createDimension('time', None)
        ds.createDimension('x', 2)
        var = ds.createVariable('v', 'f8', ('time', 'x'), fill_value=-99)
        if records:
            var[:] = records
    if expected is ValueError:
        with pytest.raises(ValueError):
            _range(path)
    elif expected == 'nan':
        assert all(np.isnan(_range(path)))
    else:
        assert _range(path) == expected


def test_the_sources_tree_shows_each_range(tmp_path):
    """The tree's [min .. max] for a variable is the cached dataset range."""
    pytest.importorskip('PySide6')
    path = tmp_path / 'tree.nc'
    with netCDF4.Dataset(path, 'w') as ds:
        ds.createDimension('time', None)
        ds.createVariable('time', 'i4', ('time',))[:] = [1, 2]
        ds.createDimension('x', 3)
        ds.createVariable('x', 'i4', ('x',))[:] = [0, 1, 2]
        ds.createVariable('v', 'f8', ('time', 'x'))[:] = [[np.nan, 2.0, 3.0], [4.0, 7.0, 5.0]]
    script = '''
import sys
from PySide6.QtWidgets import QApplication
from gelb.visualization.gui.main_window import GeLBViewMainWindow
app = QApplication([])
window = GeLBViewMainWindow()
window.open_file(sys.argv[1])
source = window._source_tree.topLevelItem(0)
texts = {source.child(i).text(0): source.child(i).text(1) for i in range(source.childCount())}
assert texts['v'].endswith('[2 .. 7]'), texts
assert window._datasets[sys.argv[1]]._range_cache['v'] == (2.0, 7.0)
window.close_file(sys.argv[1])
window.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(path)],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
