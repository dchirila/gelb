"""
Data visualization for GeLB simulation output (NetCDF files).

Reads .nc files produced by GeLB-compiled simulations, auto-detects
the spatial dimensionality, and produces appropriate plots.
"""

import warnings

import netCDF4 as nc
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from gelb.visualization.common import create_figure, add_colorbar, finish_figure


class GeLBDataset:
    """Wrapper around a GeLB-produced NetCDF file."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.ds = nc.Dataset(filepath, 'r')
        self._detect_dimensions()
        self._detect_variables()

    def _detect_dimensions(self):
        """Auto-detect spatial dimensionality (1D, 2D, 3D)."""
        self.spatial_dims = []
        for name in ['x', 'y', 'z']:
            if name in self.ds.dimensions:
                self.spatial_dims.append(name)
        self.ndim = len(self.spatial_dims)
        self.has_time = 'time' in self.ds.dimensions
        self.ntimesteps = len(self.ds.dimensions['time']) if self.has_time else 0

    def _detect_variables(self):
        """Find gauge output variables (exclude coordinate variables)."""
        coord_names = set(self.spatial_dims + ['time'])
        self.variables = {
            name: var for name, var in self.ds.variables.items()
            if name not in coord_names
        }

    def get_variable(self, name):
        """Return variable data as a numpy array."""
        return self.ds.variables[name][:]

    def get_variable_at_timestep(self, name, timestep):
        """Return variable data for a single timestep (avoids loading all)."""
        return self.ds.variables[name][timestep, ...]

    def get_variable_range(self, name):
        """Return (min, max) across all timesteps, ignoring NaN and masked
        values, cached after first call.

        Reads one record at a time, so that a large 3D output need not fit
        in memory at once.
        """
        if not hasattr(self, '_range_cache'):
            self._range_cache = {}
        if name not in self._range_cache:
            var = self.ds.variables[name]
            if var.dimensions[:1] == ('time',):
                records = (var[r, ...] for r in range(var.shape[0]))
            else:
                records = [var[:]]
            lows, highs = [], []
            with warnings.catch_warnings():
                # An all-NaN record has no range; the other records decide.
                warnings.simplefilter('ignore', RuntimeWarning)
                for record in records:
                    record = np.ma.filled(
                        np.ma.asarray(record, dtype=float), np.nan)
                    lows.append(np.nanmin(record))
                    highs.append(np.nanmax(record))
            self._range_cache[name] = (float(np.nanmin(lows)),
                                       float(np.nanmax(highs)))
        return self._range_cache[name]

    def get_coord(self, name):
        """Return coordinate values as a numpy array."""
        return self.ds.variables[name][:]

    def timestep_value(self, record_index):
        """Map a record index to the actual simulation timestep.

        When --write-every is used, the record index (0, 1, 2, ...)
        differs from the actual timestep (e.g. 10, 20, 30, ...).
        Returns the integer timestep stored in the 'time' coordinate.
        """
        if self.has_time and 'time' in self.ds.variables:
            return int(self.ds.variables['time'][record_index])
        return record_index

    def close(self):
        self.ds.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def summary(self):
        """Return a human-readable summary string."""
        lines = [
            f"File: {self.filepath}",
            f"Dimensions: {self.ndim}D ({', '.join(self.spatial_dims)})",
            f"Timesteps: {self.ntimesteps}",
            "Variables:",
        ]
        for name, var in self.variables.items():
            dims_str = ', '.join(var.dimensions)
            lines.append(f"  {name}: ({dims_str}) {var.shape}")
        return '\n'.join(lines)


# ---------------------------------------------------------------------------
# 1D visualization
# ---------------------------------------------------------------------------

def plot_1d(dataset, variables=None, output=None):
    """Space-time heatmap for 1D data.

    Each gauge variable is shown as a heatmap with x-axis = space,
    y-axis = time.  When there is only one timestep, falls back to a
    line plot (spatial profile).
    """
    vars_to_plot = variables or list(dataset.variables.keys())
    n_timesteps = dataset.ntimesteps
    fig, axes = create_figure(len(vars_to_plot), title=dataset.filepath)

    for ax, varname in zip(axes, vars_to_plot):
        data = dataset.get_variable(varname)  # shape: (time, x)
        x = dataset.get_coord('x')

        if n_timesteps <= 1:
            # Single timestep: line plot (spatial profile)
            ax.plot(x, data[0, :], marker='o', markersize=4)
            ax.set_xlabel('x')
            ax.set_ylabel(varname)
            ax.set_title(f'{varname} (t={dataset.timestep_value(0)})')
        else:
            # Multiple timesteps: space-time heatmap
            im = ax.imshow(
                data, aspect='auto', origin='lower',
                extent=[x[0], x[-1], 0, data.shape[0] - 1],
            )
            ax.set_xlabel('x')
            ax.set_ylabel('timestep')
            ax.set_title(varname)
            add_colorbar(fig, ax, im)

    finish_figure(fig, output)


# ---------------------------------------------------------------------------
# 2D visualization
# ---------------------------------------------------------------------------

def plot_2d(dataset, variables=None, timestep=-1, output=None, animate=False):
    """Heatmap for 2D data at a given timestep, or animation."""
    vars_to_plot = variables or list(dataset.variables.keys())
    if animate:
        _animate_2d(dataset, vars_to_plot, output)
    else:
        _snapshot_2d(dataset, vars_to_plot, timestep, output)


def _snapshot_2d(dataset, vars_to_plot, timestep, output):
    """Single-timestep 2D heatmap."""
    fig, axes = create_figure(len(vars_to_plot), title=dataset.filepath)

    for ax, varname in zip(axes, vars_to_plot):
        data = dataset.get_variable(varname)  # (time, y, x)
        slice_data = data[timestep, :, :]
        im = ax.imshow(slice_data, origin='lower', aspect='equal')
        ax.set_xlabel('x')
        ax.set_ylabel('y')
        ax.set_title(f'{varname} (t={dataset.timestep_value(timestep)})')
        add_colorbar(fig, ax, im)

    finish_figure(fig, output)


def _animate_2d(dataset, vars_to_plot, output):
    """Animate 2D data over time (first variable)."""
    varname = vars_to_plot[0]
    data = dataset.get_variable(varname)  # (time, y, x)
    n_frames = data.shape[0]

    vmin, vmax = float(np.nanmin(data)), float(np.nanmax(data))

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(data[0, :, :], origin='lower', aspect='equal',
                   vmin=vmin, vmax=vmax)
    ax.set_xlabel('x')
    ax.set_ylabel('y')
    title = ax.set_title(f'{varname} (t={dataset.timestep_value(0)})')
    fig.colorbar(im, ax=ax)

    def update(frame):
        frame_data = data[frame, :, :]
        im.set_data(frame_data)
        title.set_text(f'{varname} (t={dataset.timestep_value(frame)})')
        return im, title

    ani = animation.FuncAnimation(
        fig, update, frames=n_frames, interval=100, blit=False,
    )

    if output:
        ani.save(output, writer='pillow', fps=10)
        plt.close(fig)
    else:
        plt.show()


# ---------------------------------------------------------------------------
# 3D visualization
# ---------------------------------------------------------------------------

def plot_3d(dataset, variables=None, timestep=-1,
            slice_axis='z', slice_index=None, output=None):
    """Slice views for 3D data at a given timestep."""
    vars_to_plot = variables or list(dataset.variables.keys())
    fig, axes = create_figure(len(vars_to_plot), title=dataset.filepath)

    # Python netCDF4 reverses Fortran dim order: (time, z, y, x)
    axis_map = {'x': 2, 'y': 1, 'z': 0}
    ax_idx = axis_map[slice_axis]
    remaining = [a for a in ['z', 'y', 'x'] if a != slice_axis]

    for ax, varname in zip(axes, vars_to_plot):
        data = dataset.get_variable(varname)  # (time, z, y, x)
        if slice_index is None:
            si = data.shape[ax_idx + 1] // 2  # +1 for time dim
        else:
            si = slice_index

        # Build slicer: [timestep, :, :, :] then fix one spatial axis
        slicer = [timestep] + [slice(None)] * 3
        slicer[ax_idx + 1] = si
        slice_data = data[tuple(slicer)]

        im = ax.imshow(slice_data, origin='lower', aspect='equal')
        ax.set_xlabel(remaining[1])
        ax.set_ylabel(remaining[0])
        ax.set_title(f'{varname} ({slice_axis}={si}, t={dataset.timestep_value(timestep)})')
        add_colorbar(fig, ax, im)

    finish_figure(fig, output)
