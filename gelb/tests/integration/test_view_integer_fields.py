"""An integer field is drawn with the colours of its values.

matplotlib resamples an integer image whose range is at most 1e8 in
float32, which rounds every value above 2**24, so an ``int64`` gauge
field near 3e9 showed one or two colours per row.  gelb-view hands every
image float64 instead (``gelb.visualization.common.image_data``).  The
field ``3000000000 + x + 100 r`` (``r`` the row: ``y``, or the record
in a 1-D heatmap) spans 764 values over 256 colours, so a row of 64
cells shows about 21 colours.  Every path that draws a gauge field as
an image is checked, headless and in a subprocess like the other
gelb-view tests; a real field and a small integer field look as before.
"""
import os
import subprocess
import sys

import pytest

netCDF4 = pytest.importorskip('netCDF4')
np = pytest.importorskip('numpy')

BIG = 3000000000
NX, NY, NZ = 64, 8, 3

# Colours per cell row of an image, sampled at each row's centre from the
# drawn pixels.
COLOURS = '''
import numpy as np
def colours_per_row(fig, im):
    if not hasattr(fig.canvas, 'buffer_rgba'):  # closed after saving
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        FigureCanvasAgg(fig)
    fig.canvas.draw()
    rgba = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
    height, width = rgba.shape[:2]
    scale = width / fig.bbox.width
    left, right, bottom, top = im.get_extent()
    rows = im.get_array().shape[0]
    counts = []
    for r in range(rows):
        yc = bottom + (r + 0.5) * (top - bottom) / rows
        xs = np.linspace(left, right, 2000)[5:-5]
        pts = im.axes.transData.transform(np.c_[xs, np.full_like(xs, yc)])
        px = {tuple(rgba[int(height - y * scale), int(x * scale)])
              for x, y in pts}
        counts.append(len(px))
    return counts
'''

HEADLESS = COLOURS + '''
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from gelb.visualization import data_viewer
from gelb.visualization.data_viewer import GeLBDataset

path, how, gif = sys.argv[1], sys.argv[2], sys.argv[3]
figures = []
data_viewer.finish_figure = lambda fig, output=None: figures.append(fig)
subplots = plt.subplots
def recording_subplots(*args, **kwargs):
    fig, ax = subplots(*args, **kwargs)
    figures.append(fig)
    return fig, ax
data_viewer.plt.subplots = recording_subplots
def image_of(fig):
    [im] = [im for ax in fig.axes for im in ax.get_images()]
    return im
counts = []
with GeLBDataset(path) as ds:
    if how == 'plot_1d':
        data_viewer.plot_1d(ds, ['v'])
    elif how == 'plot_2d':
        data_viewer.plot_2d(ds, ['v'])
    elif how == 'animate_2d':
        # The first frame comes from imshow, the last from set_data.
        animation = data_viewer.animation.FuncAnimation
        def recording_animation(fig, *args, **kwargs):
            counts.extend(colours_per_row(fig, image_of(fig)))
            return animation(fig, *args, **kwargs)
        data_viewer.animation.FuncAnimation = recording_animation
        data_viewer.plot_2d(ds, ['v'], animate=True, output=gif)
    elif how == 'plot_3d':
        data_viewer.plot_3d(ds, ['v'])
    fig = figures[-1]
    counts.extend(colours_per_row(fig, image_of(fig)))
print(min(counts))
'''

GUI = COLOURS + '''
import sys
from PySide6.QtWidgets import QApplication
from gelb.visualization.data_viewer import GeLBDataset
from gelb.visualization.gui.plot_panel import PlotDockWidget
from gelb.visualization.gui.composite_plot_panel import CompositePlotDockWidget

app = QApplication([])
path, how = sys.argv[1], sys.argv[2]
with GeLBDataset(path) as ds:
    if how == 'side_by_side':
        panel = CompositePlotDockWidget(path, ds, ['v', 'w'], 'Side-by-Side', 0)
        images = panel._images
    else:
        panel = PlotDockWidget(path, ds, 'v', 'Heatmap', 0)
        if how == 'heatmap_other_record':
            # The slider opens at the last record; moving it to the first
            # redraws through set_data.
            panel._timestep_slider._slider.setValue(0)
            assert panel._ax.get_title().endswith('(t=0)'), panel._ax.get_title()
        images = [panel._im]
    print(min(min(colours_per_row(panel._fig, im)) for im in images))
    panel.close()
'''


def _write(path, ndim, dtype, base=BIG):
    """A field ``base + x + 100 r`` of ``dtype``: rows ``r`` are the
    records in 1-D (8 of them), ``y`` otherwise (2 records)."""
    dims = {1: ['x'], 2: ['y', 'x'], 3: ['z', 'y', 'x']}[ndim]
    sizes = {'x': NX, 'y': NY, 'z': NZ}
    records = 8 if ndim == 1 else 2
    with netCDF4.Dataset(path, 'w') as ds:
        ds.createDimension('time', None)
        ds.createVariable('time', 'i4', ('time',))[:] = list(range(records))
        for dim in dims:
            ds.createDimension(dim, sizes[dim])
            ds.createVariable(dim, 'i4', (dim,))[:] = list(range(sizes[dim]))
        shape = [records] + [sizes[d] for d in dims]
        grid = np.indices(shape)
        row = grid[0] if ndim == 1 else grid[-2]
        values = base + grid[-1] + 100 * row
        for name in ('v', 'w'):
            ds.createVariable(name, dtype, ('time', *dims))[:] = values
    return path


def _run(script, *args, gui=False):
    env = dict(os.environ)
    if gui:
        pytest.importorskip('PySide6')
        env['QT_QPA_PLATFORM'] = 'offscreen'
    else:
        env['MPLBACKEND'] = 'Agg'
    result = subprocess.run([sys.executable, '-c', script, *map(str, args)],
                            env=env, capture_output=True, text=True,
                            timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    return int(result.stdout.split()[-1])


HEADLESS_PATHS = [(1, 'plot_1d'), (2, 'plot_2d'), (2, 'animate_2d'),
                  (3, 'plot_3d')]
GUI_PATHS = [(1, 'heatmap'), (2, 'heatmap'), (2, 'heatmap_other_record'),
             (3, 'heatmap'), (2, 'side_by_side')]


@pytest.mark.parametrize('dtype', ['i8', 'f8'])
@pytest.mark.parametrize(('ndim', 'how'), HEADLESS_PATHS)
def test_gelb_view_draws_every_row_of_a_large_integer_field(
        tmp_path, ndim, how, dtype):
    path = _write(tmp_path / 'data.nc', ndim, dtype)
    assert _run(HEADLESS, path, how, tmp_path / 'anim.gif') >= 15


@pytest.mark.parametrize('dtype', ['i8', 'f8'])
@pytest.mark.parametrize(('ndim', 'how'), GUI_PATHS)
def test_the_window_draws_every_row_of_a_large_integer_field(
        tmp_path, ndim, how, dtype):
    path = _write(tmp_path / 'data.nc', ndim, dtype)
    assert _run(GUI, path, how, gui=True) >= 15


def test_image_data_converts_only_integers():
    from gelb.visualization.common import image_data
    for dtype in (np.int8, np.int16, np.int32, np.int64, np.uint8, bool):
        values = np.ma.array(np.array([[1, 0], [1, 1]], dtype=dtype),
                             mask=[[False, True], [False, False]])
        image = image_data(values)
        assert image.dtype == np.float64, dtype
        assert image.mask.tolist() == values.mask.tolist(), dtype
        assert image.filled(-1).tolist() == [[1.0, -1.0], [1.0, 1.0]], dtype
    assert image_data(np.int64(BIG + 1) * np.ones(2, np.int64)).tolist() \
        == [BIG + 1.0, BIG + 1.0]
    for dtype in (np.float32, np.float64):
        values = np.ma.array(np.arange(4, dtype=dtype).reshape(2, 2))
        assert image_data(values) is values, dtype


SAME_PIXELS = '''
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from gelb.visualization.common import image_data
y, x = np.mgrid[0:8, 0:64]
values = (x + 100 * y).astype(sys.argv[1])
def pixels(data):
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.imshow(data, origin='lower', aspect='equal')
    fig.canvas.draw()
    return np.asarray(fig.canvas.buffer_rgba()).copy()
print(int(np.array_equal(pixels(values), pixels(image_data(values)))))
'''


@pytest.mark.parametrize('dtype', ['int16', 'int32', 'int64'])
def test_a_small_integer_field_looks_as_before(dtype):
    assert _run(SAME_PIXELS, dtype) == 1
