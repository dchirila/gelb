"""gelb-view's figures: a basename title and a colour bar as tall as the plot.

The headless viewer (``gelb-view data.nc -o fig.png``) titles the figure
with the file's name, not its full path, and every colour bar, headless
or in the window, spans exactly the drawn image, also for a wide grid,
where an equal-aspect image fills only part of its axes box (user manual,
chapter 2, "Viewing results").
"""
import os
from pathlib import Path
import subprocess
import sys

import matplotlib
matplotlib.use('Agg')
import numpy as np
import pytest

netCDF4 = pytest.importorskip('netCDF4')

from gelb.visualization import data_viewer  # noqa: E402

SIZES = {'x': 20, 'y': 4, 'z': 3}     # wide in x: the hard case for a colour bar


def write_data(path, ndim):
    dims = ['z', 'y', 'x'][3 - ndim:]
    with netCDF4.Dataset(path, 'w') as ds:
        ds.createDimension('time', None)
        ds.createVariable('time', 'i4', ('time',))[:] = [0, 1, 2]
        for dim in dims:
            ds.createDimension(dim, SIZES[dim])
            ds.createVariable(dim, 'i4', (dim,))[:] = list(range(SIZES[dim]))
        shape = [SIZES[dim] for dim in dims]
        ds.createVariable('value', 'f8', ('time', *dims))[:] = np.random.default_rng(0).random((3, *shape))


def heights(fig):
    """(image axes height, colour bar axes height) after a draw."""
    fig.canvas.draw()
    image, bar = fig.axes[0], fig.axes[1]
    return image.get_position().height, bar.get_position().height


@pytest.mark.parametrize(('ndim', 'plot'), [
    (1, data_viewer.plot_1d), (2, data_viewer.plot_2d), (3, data_viewer.plot_3d)])
def test_headless_figure_title_and_colorbar(tmp_path, monkeypatch, ndim, plot):
    path = tmp_path / 'sub' / 'data.nc'
    path.parent.mkdir()
    write_data(path, ndim)
    figures = []
    monkeypatch.setattr(data_viewer, 'finish_figure', lambda fig, output=None, **kw: figures.append(fig))
    dataset = data_viewer.GeLBDataset(str(path))
    try:
        plot(dataset, variables=['value'], output=str(tmp_path / 'fig.png'))
    finally:
        dataset.close()
    [fig] = figures
    assert fig._suptitle.get_text() == 'data.nc'
    fig.tight_layout()
    image, bar = heights(fig)
    assert bar == pytest.approx(image, abs=1e-6)
    matplotlib.pyplot.close(fig)


@pytest.mark.parametrize('ndim', [2, 3])
def test_window_colorbar_follows_the_image(tmp_path, ndim):
    path = tmp_path / 'data.nc'
    write_data(path, ndim)
    script = '''
import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from gelb.visualization.data_viewer import GeLBDataset
from gelb.visualization.gui.plot_panel import PlotDockWidget
app = QApplication([])
dataset = GeLBDataset(sys.argv[1])
window = QMainWindow()
panel = PlotDockWidget(sys.argv[1], dataset, 'value', 'Heatmap', 0)
window.setCentralWidget(panel)
for width, height in [(700, 500), (400, 700)]:
    window.resize(width, height)
    window.show()
    app.processEvents()
    panel._canvas.draw()
    image = panel._ax.get_position().height
    bar = panel._colorbar.ax.get_position().height
    assert abs(image - bar) < 1e-6, (width, height, image, bar)
panel.close()
dataset.close()
'''
    result = subprocess.run([sys.executable, '-c', script, str(path)],
                            env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
