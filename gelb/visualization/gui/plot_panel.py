"""
Dockable plot panel embedding a matplotlib figure.

Each PlotDockWidget contains:
  - FigureCanvasQTAgg (the matplotlib plot)
  - NavigationToolbar2QT (zoom/pan/save)
  - Control widgets (timestep slider, colormap, etc.)
"""

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QPushButton,
)

from gelb.visualization.gui.plot_controllers import (
    TimestepSlider,
    ColormapSelector,
    SliceControls,
    AnimationControls,
)


class PlotDockWidget(QDockWidget):
    """A dockable, snappable plot panel."""

    closed = Signal(int)  # plot_id

    def __init__(self, filepath, dataset, var_name, plot_type,
                 plot_id, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self._dataset = dataset
        self._var_name = var_name
        self._plot_type = plot_type
        self._plot_id = plot_id

        # Control widgets (must be set before _update_title)
        self._timestep_slider = None
        self._cmap_selector = None
        self._slice_controls = None
        self._anim_controls = None

        self._update_title()
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable)

        # Matplotlib figure (not via pyplot)
        self._fig = Figure(tight_layout=True)
        self._ax = self._fig.add_subplot(111)
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)

        # Internal plot state
        self._im = None          # imshow AxesImage
        self._line = None        # line plot Line2D
        self._colorbar = None
        self._autoscale_y = False  # fixed Y-axis by default for line plots
        self._global_ymin = None
        self._global_ymax = None
        self._global_vmin = None   # fixed colormap range for heatmaps
        self._global_vmax = None

        # Build the widget layout
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas, stretch=1)

        self._setup_controls(layout)
        self.setWidget(container)

        # Initial render
        self._render()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_controls(self, layout):
        ndim = self._dataset.ndim
        n_ts = self._dataset.ntimesteps

        if self._plot_type == 'Animation' and n_ts > 1:
            self._anim_controls = AnimationControls(n_ts, self)
            self._anim_controls.frame_tick.connect(self._on_timestep_change)
            layout.addWidget(self._anim_controls)
        elif n_ts > 1:
            self._timestep_slider = TimestepSlider(n_ts, self)
            self._timestep_slider.timestep_changed.connect(
                self._on_timestep_change)
            layout.addWidget(self._timestep_slider)

        # Auto-scale Y toggle for line plots
        if self._plot_type == 'Line Plot' or (
                ndim == 1 and n_ts <= 1):
            self._autoscale_btn = QPushButton('Auto Y: Off')
            self._autoscale_btn.setCheckable(True)
            self._autoscale_btn.setChecked(False)
            self._autoscale_btn.toggled.connect(self._on_autoscale_toggle)
            layout.addWidget(self._autoscale_btn)

        # Colormap for heatmaps (not line plots on 1D single-timestep)
        if not (self._plot_type == 'Line Plot'
                or (ndim == 1 and n_ts <= 1)):
            self._cmap_selector = ColormapSelector(self)
            self._cmap_selector.colormap_changed.connect(
                self._on_colormap_change)
            layout.addWidget(self._cmap_selector)

        # Slice controls for cross-section (2D+) and 3D slice
        if self._plot_type == 'Cross-Section' and ndim >= 2:
            shape_dict = {}
            for dim_name in self._dataset.spatial_dims:
                shape_dict[dim_name] = len(
                    self._dataset.ds.dimensions[dim_name])
            self._slice_controls = SliceControls(shape_dict, self)
            self._slice_controls.slice_changed.connect(
                self._on_slice_change)
            layout.addWidget(self._slice_controls)

            self._autoscale_btn = QPushButton('Auto Y: Off')
            self._autoscale_btn.setCheckable(True)
            self._autoscale_btn.setChecked(False)
            self._autoscale_btn.toggled.connect(self._on_autoscale_toggle)
            layout.addWidget(self._autoscale_btn)

        # Slice controls for 3D
        if self._plot_type != 'Cross-Section' and ndim == 3:
            shape_dict = {}
            for dim_name in self._dataset.spatial_dims:
                shape_dict[dim_name] = len(
                    self._dataset.ds.dimensions[dim_name])
            self._slice_controls = SliceControls(shape_dict, self)
            self._slice_controls.slice_changed.connect(
                self._on_slice_change)
            layout.addWidget(self._slice_controls)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self):
        """Initial full render."""
        ndim = self._dataset.ndim

        if self._plot_type == 'Cross-Section' and ndim >= 2:
            self._render_cross_section()
        elif (self._plot_type == 'Line Plot' and ndim == 1) or (
                ndim == 1
                and self._dataset.ntimesteps <= 1
                and self._plot_type != 'Heatmap'):
            self._render_line()
        elif ndim == 1:
            self._render_1d_heatmap()
        elif ndim == 2:
            self._render_2d_heatmap()
        elif ndim == 3:
            self._render_3d_slice()

        self._canvas.draw_idle()

    def _render_line(self):
        """Render a line plot (1D spatial profile at a timestep)."""
        ts = self._current_timestep()
        data = self._dataset.get_variable_at_timestep(self._var_name, ts)
        x = self._dataset.get_coord('x')

        # Compute global Y range across all timesteps (once)
        if self._global_ymin is None:
            all_data = self._dataset.get_variable(self._var_name)
            self._global_ymin = float(np.nanmin(all_data))
            self._global_ymax = float(np.nanmax(all_data))

        self._ax.clear()
        self._line, = self._ax.plot(x, data, marker='o', markersize=3)
        self._ax.set_xlabel('x')
        self._ax.set_ylabel(self._var_name)
        self._ax.set_title(f'{self._var_name} (t={self._dataset.timestep_value(ts)})')

        if not self._autoscale_y:
            margin = (self._global_ymax - self._global_ymin) * 0.05
            self._ax.set_ylim(self._global_ymin - margin,
                              self._global_ymax + margin)

    def _render_cross_section(self):
        """Render a 1D cross-section through 2D (or higher) data."""
        ts = self._current_timestep()
        data = self._dataset.get_variable_at_timestep(self._var_name, ts)

        # Determine slice axis and index
        # For 2D data (y, x): slicing along y gives a row (profile in x),
        #                      slicing along x gives a column (profile in y)
        ndim = self._dataset.ndim
        axis_map = {'x': -1, 'y': -2, 'z': -3}
        if self._slice_controls:
            axis_name = self._slice_controls.axis()
            slice_idx = self._slice_controls.index()
        else:
            axis_name = self._dataset.spatial_dims[-1]
            slice_idx = data.shape[axis_map[axis_name]] // 2

        ax_idx = axis_map[axis_name]
        slicer = [slice(None)] * ndim
        slicer[ax_idx] = slice_idx
        line_data = data[tuple(slicer)]

        # The remaining axis is what we plot along
        remaining = [d for d in self._dataset.spatial_dims if d != axis_name]
        plot_axis = remaining[0] if remaining else 'x'
        x = self._dataset.get_coord(plot_axis)

        # Compute global Y range across all timesteps (once)
        if self._global_ymin is None:
            all_data = self._dataset.get_variable(self._var_name)
            self._global_ymin = float(np.nanmin(all_data))
            self._global_ymax = float(np.nanmax(all_data))

        self._ax.clear()
        self._line, = self._ax.plot(x, line_data, marker='o', markersize=3)
        self._ax.set_xlabel(plot_axis)
        self._ax.set_ylabel(self._var_name)
        self._ax.set_title(
            f'{self._var_name} ({axis_name}={slice_idx}, '
            f't={self._dataset.timestep_value(ts)})')

        if not self._autoscale_y:
            margin = (self._global_ymax - self._global_ymin) * 0.05
            if margin == 0:
                margin = 0.1
            self._ax.set_ylim(self._global_ymin - margin,
                              self._global_ymax + margin)

    def _render_1d_heatmap(self):
        """Render a space-time heatmap for 1D data (all timesteps)."""
        data = self._dataset.get_variable(self._var_name)  # (time, x)
        x = self._dataset.get_coord('x')
        cmap = self._current_cmap()

        self._ax.clear()
        self._colorbar = None
        self._im = self._ax.imshow(
            data, aspect='auto', origin='lower',
            extent=[x[0], x[-1], 0, data.shape[0] - 1],
            cmap=cmap,
        )
        self._ax.set_xlabel('x')
        self._ax.set_ylabel('timestep')
        self._ax.set_title(self._var_name)
        self._colorbar = self._fig.colorbar(self._im, ax=self._ax)

    def _render_2d_heatmap(self):
        """Render a 2D heatmap at a given timestep."""
        ts = self._current_timestep()
        data = self._dataset.get_variable_at_timestep(self._var_name, ts)
        cmap = self._current_cmap()

        if self._global_vmin is None:
            self._global_vmin, self._global_vmax = \
                self._dataset.get_variable_range(self._var_name)

        self._ax.clear()
        self._colorbar = None
        self._im = self._ax.imshow(
            data, origin='lower', aspect='equal', cmap=cmap,
            vmin=self._global_vmin, vmax=self._global_vmax)
        self._ax.set_xlabel('x')
        self._ax.set_ylabel('y')
        self._ax.set_title(f'{self._var_name} (t={self._dataset.timestep_value(ts)})')
        self._colorbar = self._fig.colorbar(self._im, ax=self._ax)

    def _render_3d_slice(self):
        """Render a 2D slice of 3D data."""
        ts = self._current_timestep()
        data = self._dataset.get_variable_at_timestep(self._var_name, ts)
        cmap = self._current_cmap()

        # Python netCDF4 reverses Fortran dim order: (z, y, x)
        axis_map = {'x': 2, 'y': 1, 'z': 0}
        axis_name = 'z'
        ax_idx = axis_map[axis_name]
        slice_idx = data.shape[ax_idx] // 2
        if self._slice_controls:
            axis_name = self._slice_controls.axis()
            ax_idx = axis_map[axis_name]
            slice_idx = self._slice_controls.index()

        remaining = [a for a in ['z', 'y', 'x'] if a != axis_name]

        slicer = [slice(None)] * 3
        slicer[ax_idx] = slice_idx
        slice_data = data[tuple(slicer)]

        self._ax.clear()
        self._colorbar = None
        self._im = self._ax.imshow(
            slice_data, origin='lower', aspect='equal', cmap=cmap)
        self._ax.set_xlabel(remaining[1])
        self._ax.set_ylabel(remaining[0])
        self._ax.set_title(
            f'{self._var_name} ({axis_name}={slice_idx}, t={self._dataset.timestep_value(ts)})')
        self._colorbar = self._fig.colorbar(self._im, ax=self._ax)

    # ------------------------------------------------------------------
    # Update methods (in-place, no full replot)
    # ------------------------------------------------------------------

    def _on_timestep_change(self, ts):
        """Update plot for a new timestep."""
        if not self._dataset.ds.isopen():
            return
        ndim = self._dataset.ndim

        if self._plot_type == 'Cross-Section':
            self._render_cross_section()
            self._update_title()
            self._canvas.draw_idle()
            return

        if self._plot_type == 'Line Plot' or (
                ndim == 1 and self._dataset.ntimesteps <= 1):
            data = self._dataset.get_variable_at_timestep(self._var_name, ts)
            if self._line is not None:
                self._line.set_ydata(data)
                self._ax.set_title(f'{self._var_name} (t={self._dataset.timestep_value(ts)})')
                if self._autoscale_y:
                    self._ax.autoscale(enable=True, axis='y')
                    self._ax.relim()
                    self._ax.autoscale_view()
            else:
                self._render_line()
        elif ndim == 2:
            data = self._dataset.get_variable_at_timestep(self._var_name, ts)
            if self._im is not None:
                self._im.set_data(data)
                self._ax.set_title(f'{self._var_name} (t={self._dataset.timestep_value(ts)})')
            else:
                self._render_2d_heatmap()
        elif ndim == 3:
            self._render_3d_slice()

        self._update_title()
        self._canvas.draw_idle()

    def _on_autoscale_toggle(self, checked):
        """Toggle between fixed and auto Y-axis scaling."""
        self._autoscale_y = checked
        self._autoscale_btn.setText(
            'Auto Y: On' if checked else 'Auto Y: Off')
        if self._line is not None:
            if checked:
                self._ax.autoscale(enable=True, axis='y')
                self._ax.relim()
                self._ax.autoscale_view()
            else:
                margin = (self._global_ymax - self._global_ymin) * 0.05
                self._ax.set_ylim(self._global_ymin - margin,
                                  self._global_ymax + margin)
            self._canvas.draw_idle()

    def _on_colormap_change(self, cmap_name):
        """Update colormap in-place."""
        if self._im is not None:
            self._im.set_cmap(cmap_name)
            self._canvas.draw_idle()

    def _on_slice_change(self, axis, index):
        """Update slice (3D slice or cross-section)."""
        if not self._dataset.ds.isopen():
            return
        if self._plot_type == 'Cross-Section':
            self._render_cross_section()
        else:
            self._render_3d_slice()
        self._update_title()
        self._canvas.draw_idle()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_timestep(self):
        if self._anim_controls:
            return self._anim_controls._current_frame
        if self._timestep_slider:
            return self._timestep_slider.value()
        return self._dataset.ntimesteps - 1 if self._dataset.ntimesteps > 0 else 0

    def _current_cmap(self):
        if self._cmap_selector:
            return self._cmap_selector.value()
        return 'viridis'

    def _update_title(self):
        ts = self._current_timestep()
        title = f'{self._var_name} [{self._plot_type}]'
        if self._dataset.ntimesteps > 1:
            title += f' t={self._dataset.timestep_value(ts)}'
        self.setWindowTitle(title)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        import warnings
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                self._fig.tight_layout()
            self._canvas.draw_idle()
        except Exception:
            pass  # tight_layout can fail during init or at small sizes

    def closeEvent(self, event):
        if self._anim_controls:
            self._anim_controls.stop()
        self.closed.emit(self._plot_id)
        super().closeEvent(event)
