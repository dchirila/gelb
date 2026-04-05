"""
Composite plot panel for multi-variable visualizations.

Supports:
  - Side-by-Side: one subplot per variable
  - Vector Field: quiver plot from two velocity components
  - Magnitude: sqrt(v1^2 + v2^2 [+ v3^2]) heatmap
  - Vorticity: (dvx/dy - dvy/dx) heatmap (2D only)
  - Particle Animation: tracer advection through velocity field
"""

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton,
)

from gelb.visualization.gui.plot_controllers import (
    TimestepSlider,
    ColormapSelector,
    AnimationControls,
)


class CompositePlotDockWidget(QDockWidget):
    """A dockable plot panel combining multiple variables."""

    closed = Signal(int)  # plot_id

    def __init__(self, filepath, dataset, var_names, plot_type,
                 plot_id, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self._dataset = dataset
        self._var_names = var_names
        self._plot_type = plot_type
        self._plot_id = plot_id

        # Control widgets
        self._timestep_slider = None
        self._cmap_selector = None
        self._anim_controls = None
        self._density_spin = None

        label = ', '.join(var_names)
        self.setWindowTitle(f'{label} [{plot_type}]')
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable)

        # Matplotlib figure
        self._fig = Figure(tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._toolbar = NavigationToolbar2QT(self._canvas, self)

        # Internal state
        self._axes = []
        self._images = []
        self._colorbars = []
        self._quiver = None
        self._streamplot = None
        self._scatter = None
        self._particle_positions = None
        self._fluid_mask = None
        self._seeding_mask = None
        self._particle_count_spin = None
        self._wall_margin_spin = None
        self._global_vmin = None
        self._global_vmax = None

        # Build layout
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
        n_ts = self._dataset.ntimesteps

        if n_ts > 1:
            self._anim_controls = AnimationControls(n_ts, self)
            self._anim_controls.frame_tick.connect(self._on_timestep_change)
            layout.addWidget(self._anim_controls)

        if self._plot_type in ('Magnitude', 'Vorticity', 'Side-by-Side'):
            self._cmap_selector = ColormapSelector(self)
            self._cmap_selector.colormap_changed.connect(
                self._on_colormap_change)
            layout.addWidget(self._cmap_selector)

        if self._plot_type == 'Vector Field':
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(QLabel('Arrow density:'))
            self._density_spin = QSpinBox()
            self._density_spin.setRange(1, 20)
            self._density_spin.setValue(2)
            self._density_spin.valueChanged.connect(
                lambda _: self._render_vector_field())
            row_layout.addWidget(self._density_spin)
            layout.addWidget(row)

        if self._plot_type == 'Streamlines':
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(QLabel('Line density:'))
            self._density_spin = QSpinBox()
            self._density_spin.setRange(1, 20)
            self._density_spin.setValue(10)
            self._density_spin.valueChanged.connect(
                lambda _: self._render_streamlines())
            row_layout.addWidget(self._density_spin)
            layout.addWidget(row)

        if self._plot_type == 'Particle Animation':
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)

            row_layout.addWidget(QLabel('Particles:'))
            self._particle_count_spin = QSpinBox()
            self._particle_count_spin.setRange(10, 5000)
            self._particle_count_spin.setValue(200)
            self._particle_count_spin.setSingleStep(50)
            row_layout.addWidget(self._particle_count_spin)

            row_layout.addWidget(QLabel('Wall margin:'))
            self._wall_margin_spin = QSpinBox()
            self._wall_margin_spin.setRange(0, 20)
            self._wall_margin_spin.setValue(3)
            self._wall_margin_spin.setToolTip(
                'Safety distance (in cells) from solid walls for seeding')
            row_layout.addWidget(self._wall_margin_spin)

            reseed_btn = QPushButton('Reseed')
            reseed_btn.clicked.connect(self._reseed_particles)
            row_layout.addWidget(reseed_btn)

            layout.addWidget(row)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self):
        if self._plot_type == 'Side-by-Side':
            self._render_side_by_side()
        elif self._plot_type == 'Vector Field':
            self._render_vector_field()
        elif self._plot_type == 'Magnitude':
            self._render_magnitude()
        elif self._plot_type == 'Vorticity':
            self._render_vorticity()
        elif self._plot_type == 'Streamlines':
            self._render_streamlines()
        elif self._plot_type == 'Particle Animation':
            self._render_particles()
        self._canvas.draw_idle()

    def _render_side_by_side(self):
        """One subplot per variable, shared colormap."""
        self._fig.clear()
        self._axes = []
        self._images = []
        self._colorbars = []

        ts = self._current_timestep()
        cmap = self._current_cmap()
        n = len(self._var_names)
        ndim = self._dataset.ndim

        for i, var_name in enumerate(self._var_names):
            ax = self._fig.add_subplot(1, n, i + 1)
            self._axes.append(ax)
            data = self._dataset.get_variable_at_timestep(var_name, ts)

            if ndim == 1:
                x = self._dataset.get_coord('x')
                ax.plot(x, data, marker='o', markersize=3)
                ax.set_xlabel('x')
            else:
                vmin, vmax = self._dataset.get_variable_range(var_name)
                im = ax.imshow(data, origin='lower', aspect='equal',
                               cmap=cmap, vmin=vmin, vmax=vmax)
                self._images.append(im)
                self._colorbars.append(self._fig.colorbar(im, ax=ax))
                ax.set_xlabel('x')
                ax.set_ylabel('y')

            ax.set_title(var_name)

        self._fig.suptitle(f't={self._dataset.timestep_value(ts)}')

    def _render_vector_field(self):
        """Quiver plot from two velocity components."""
        self._fig.clear()
        self._axes = []

        ts = self._current_timestep()
        vx = self._dataset.get_variable_at_timestep(self._var_names[0], ts)
        vy = self._dataset.get_variable_at_timestep(self._var_names[1], ts)

        ax = self._fig.add_subplot(111)
        self._axes = [ax]

        stride = self._density_spin.value() if self._density_spin else 2
        ny, nx = vx.shape
        X, Y = np.meshgrid(np.arange(nx), np.arange(ny))

        # Subsample for readability
        s = slice(None, None, stride)
        speed = np.sqrt(vx**2 + vy**2)

        self._quiver = ax.quiver(
            X[s, s], Y[s, s], vx[s, s], vy[s, s],
            speed[s, s], cmap='viridis', scale_units='xy')
        ax.set_xlabel('x')
        ax.set_ylabel('y')
        ax.set_aspect('equal')
        ax.set_title(
            f'{self._var_names[0]}, {self._var_names[1]} '
            f'(t={self._dataset.timestep_value(ts)})')
        self._fig.colorbar(self._quiver, ax=ax, label='speed')
        self._canvas.draw_idle()

    def _render_streamlines(self):
        """Streamline plot from two velocity components."""
        self._fig.clear()
        self._axes = []

        ts = self._current_timestep()
        vx = self._dataset.get_variable_at_timestep(self._var_names[0], ts)
        vy = self._dataset.get_variable_at_timestep(self._var_names[1], ts)

        ax = self._fig.add_subplot(111)
        self._axes = [ax]

        ny, nx = vx.shape
        X, Y = np.meshgrid(np.arange(nx), np.arange(ny))
        speed = np.sqrt(vx**2 + vy**2)

        # Map spinner (1-20) to density (0.1-2.0)
        density = (self._density_spin.value() / 10.0
                   if self._density_spin else 1.0)

        # Replace NaN with 0 for streamplot (solid regions)
        vx_safe = np.nan_to_num(vx, nan=0.0)
        vy_safe = np.nan_to_num(vy, nan=0.0)

        self._streamplot = ax.streamplot(
            X, Y, vx_safe, vy_safe,
            density=density,
            color=np.nan_to_num(speed, nan=0.0),
            cmap='viridis',
            linewidth=1.5,
            arrowsize=1.5,
            broken_streamlines=False)
        ax.set_xlabel('x')
        ax.set_ylabel('y')
        ax.set_aspect('equal')
        ax.set_title(
            f'{self._var_names[0]}, {self._var_names[1]} '
            f'(t={self._dataset.timestep_value(ts)})')
        self._fig.colorbar(self._streamplot.lines, ax=ax, label='speed')
        self._canvas.draw_idle()

    def _render_magnitude(self):
        """Heatmap of sqrt(v1^2 + v2^2 [+ v3^2])."""
        self._fig.clear()
        self._images = []
        self._colorbars = []

        ts = self._current_timestep()
        cmap = self._current_cmap()

        components = [
            self._dataset.get_variable_at_timestep(vn, ts)
            for vn in self._var_names
        ]
        mag = np.sqrt(sum(c**2 for c in components))

        if self._global_vmin is None:
            # Compute global range across all timesteps
            all_mag = []
            for t in range(self._dataset.ntimesteps):
                comps = [
                    self._dataset.get_variable_at_timestep(vn, t)
                    for vn in self._var_names
                ]
                all_mag.append(np.sqrt(sum(c**2 for c in comps)))
            stacked = np.stack(all_mag)
            self._global_vmin = float(np.nanmin(stacked))
            self._global_vmax = float(np.nanmax(stacked))

        ax = self._fig.add_subplot(111)
        self._axes = [ax]
        im = ax.imshow(mag, origin='lower', aspect='equal', cmap=cmap,
                       vmin=self._global_vmin, vmax=self._global_vmax)
        self._images = [im]
        ax.set_xlabel('x')
        ax.set_ylabel('y')
        label = ', '.join(self._var_names)
        ax.set_title(
            f'|({label})| (t={self._dataset.timestep_value(ts)})')
        cb = self._fig.colorbar(im, ax=ax)
        self._colorbars = [cb]

    def _render_vorticity(self):
        """Heatmap of dvx/dy - dvy/dx (2D only)."""
        self._fig.clear()
        self._images = []
        self._colorbars = []

        ts = self._current_timestep()
        cmap = 'RdBu_r'  # diverging colormap for vorticity

        vx = self._dataset.get_variable_at_timestep(self._var_names[0], ts)
        vy = self._dataset.get_variable_at_timestep(self._var_names[1], ts)

        # vorticity = dvy/dx - dvx/dy
        # data shape is (y, x), so axis=1 is x, axis=0 is y
        dvydx = np.gradient(vy, axis=1)
        dvxdy = np.gradient(vx, axis=0)
        vort = dvydx - dvxdy

        if self._global_vmin is None:
            all_vort = []
            for t in range(self._dataset.ntimesteps):
                vx_t = self._dataset.get_variable_at_timestep(
                    self._var_names[0], t)
                vy_t = self._dataset.get_variable_at_timestep(
                    self._var_names[1], t)
                all_vort.append(np.gradient(vy_t, axis=1)
                                - np.gradient(vx_t, axis=0))
            stacked = np.stack(all_vort)
            vlim = max(abs(float(np.nanmin(stacked))),
                       abs(float(np.nanmax(stacked))))
            self._global_vmin = -vlim
            self._global_vmax = vlim

        ax = self._fig.add_subplot(111)
        self._axes = [ax]
        im = ax.imshow(vort, origin='lower', aspect='equal', cmap=cmap,
                       vmin=self._global_vmin, vmax=self._global_vmax)
        self._images = [im]
        ax.set_xlabel('x')
        ax.set_ylabel('y')
        label = ', '.join(self._var_names)
        ax.set_title(
            f'vorticity({label}) (t={self._dataset.timestep_value(ts)})')
        cb = self._fig.colorbar(im, ax=ax)
        self._colorbars = [cb]

    def _render_particles(self):
        """Render tracer particles advected by the velocity field."""
        self._fig.clear()

        ts = self._current_timestep()
        vx = self._dataset.get_variable_at_timestep(self._var_names[0], ts)
        vy = self._dataset.get_variable_at_timestep(self._var_names[1], ts)
        ny, nx = vx.shape

        # Build masks on first render
        if self._fluid_mask is None:
            self._fluid_mask = ~np.isnan(vx)
            self._rebuild_seeding_mask()

        # Seed particles on first render (only in safe fluid cells)
        if self._particle_positions is None:
            n = self._particle_count_spin.value() if self._particle_count_spin else 200
            self._particle_positions = self._seed_particles(nx, ny, n)
            self._particle_trail = [self._particle_positions.copy()]

        ax = self._fig.add_subplot(111)
        self._axes = [ax]

        # Draw speed as background
        speed = np.sqrt(vx**2 + vy**2)
        ax.imshow(speed, origin='lower', aspect='equal',
                  cmap='gray_r', alpha=0.3)

        # Draw trail (fading)
        n_trail = min(len(self._particle_trail), 10)
        for i, pos in enumerate(self._particle_trail[-n_trail:]):
            alpha = 0.1 + 0.9 * (i / n_trail)
            ax.scatter(pos[:, 0], pos[:, 1], s=1, c='blue', alpha=alpha)

        # Draw current positions
        ax.scatter(self._particle_positions[:, 0],
                   self._particle_positions[:, 1],
                   s=5, c='red', zorder=10)

        ax.set_xlim(0, nx - 1)
        ax.set_ylim(0, ny - 1)
        ax.set_xlabel('x')
        ax.set_ylabel('y')
        ax.set_title(f'Particles (t={self._dataset.timestep_value(ts)})')
        self._canvas.draw_idle()

    def _rebuild_seeding_mask(self):
        """Build seeding mask by eroding the fluid mask by the wall margin.

        Uses iterative numpy-based dilation (no scipy dependency).
        """
        margin = self._wall_margin_spin.value() if self._wall_margin_spin else 3
        if margin > 0:
            # Dilate the solid mask by shifting in 4 directions per iteration
            solid = ~self._fluid_mask
            for _ in range(margin):
                padded = np.pad(solid, 1, constant_values=False)
                solid = (solid
                         | padded[1:-1, 2:]    # right
                         | padded[1:-1, :-2]   # left
                         | padded[2:, 1:-1]    # down
                         | padded[:-2, 1:-1])  # up
            self._seeding_mask = ~solid
        else:
            self._seeding_mask = self._fluid_mask.copy()

    def _seed_particles(self, nx, ny, n_particles=200):
        """Seed particles only in safe fluid cells (away from walls)."""
        rng = np.random.default_rng()
        safe_ys, safe_xs = np.where(self._seeding_mask)
        if len(safe_xs) == 0:
            # No safe cells -- fall back to raw fluid mask
            safe_ys, safe_xs = np.where(self._fluid_mask)
        if len(safe_xs) == 0:
            # No fluid cells at all -- seed uniformly as fallback
            return np.column_stack([
                rng.uniform(0, nx - 1, n_particles),
                rng.uniform(0, ny - 1, n_particles),
            ])
        # Pick random safe cells and jitter within them
        indices = rng.choice(len(safe_xs), size=n_particles, replace=True)
        return np.column_stack([
            safe_xs[indices].astype(float) + rng.uniform(-0.4, 0.4, n_particles),
            safe_ys[indices].astype(float) + rng.uniform(-0.4, 0.4, n_particles),
        ])

    def _reseed_particles(self):
        """Reseed all particles (triggered by Reseed button)."""
        if self._fluid_mask is None:
            return
        vx = self._dataset.get_variable_at_timestep(self._var_names[0], 0)
        ny, nx = vx.shape
        self._rebuild_seeding_mask()
        n = self._particle_count_spin.value() if self._particle_count_spin else 200
        self._particle_positions = self._seed_particles(nx, ny, n)
        self._particle_trail = [self._particle_positions.copy()]
        self._render_particles()

    def _interpolate_velocity(self, vx_safe, vy_safe, pos, nx, ny):
        """Bilinear interpolation of velocity at particle positions."""
        ix = np.clip(pos[:, 0].astype(int), 0, nx - 2)
        iy = np.clip(pos[:, 1].astype(int), 0, ny - 2)
        fx = pos[:, 0] - ix
        fy = pos[:, 1] - iy

        u = ((1 - fx) * (1 - fy) * vx_safe[iy, ix]
             + fx * (1 - fy) * vx_safe[iy, ix + 1]
             + (1 - fx) * fy * vx_safe[iy + 1, ix]
             + fx * fy * vx_safe[iy + 1, ix + 1])

        v = ((1 - fx) * (1 - fy) * vy_safe[iy, ix]
             + fx * (1 - fy) * vy_safe[iy, ix + 1]
             + (1 - fx) * fy * vy_safe[iy + 1, ix]
             + fx * fy * vy_safe[iy + 1, ix + 1])

        return u, v

    def _advect_particles(self, ts):
        """Advect massless tracer particles using the velocity field.

        Uses sub-stepping to trace pathlines accurately: the displacement
        per sub-step is at most 0.5 grid cells, preventing particles from
        overshooting turning points and appearing to have inertia.
        """
        vx = self._dataset.get_variable_at_timestep(self._var_names[0], ts)
        vy = self._dataset.get_variable_at_timestep(self._var_names[1], ts)
        ny, nx = vx.shape

        # Use NaN-safe copies: treat NaN (solid) velocity as zero
        vx_safe = np.nan_to_num(vx, nan=0.0)
        vy_safe = np.nan_to_num(vy, nan=0.0)

        # Determine number of sub-steps: ensure max displacement <= 0.5 cells
        max_speed = max(np.max(np.abs(vx_safe)), np.max(np.abs(vy_safe)), 1e-10)
        n_substeps = max(1, int(np.ceil(max_speed / 0.5)))

        pos = self._particle_positions
        dt = 1.0 / n_substeps

        for _ in range(n_substeps):
            u, v = self._interpolate_velocity(vx_safe, vy_safe, pos, nx, ny)
            pos[:, 0] += u * dt
            pos[:, 1] += v * dt

            # Wrap after each sub-step (periodic)
            pos[:, 0] = pos[:, 0] % nx
            pos[:, 1] = pos[:, 1] % ny

        # Respawn particles that ended up in solid cells
        pix = np.clip(pos[:, 0].astype(int), 0, nx - 1)
        piy = np.clip(pos[:, 1].astype(int), 0, ny - 1)
        in_solid = ~self._fluid_mask[piy, pix]
        if np.any(in_solid):
            n_respawn = int(np.sum(in_solid))
            new_pos = self._seed_particles(nx, ny, n_respawn)
            pos[in_solid] = new_pos

        self._particle_trail.append(pos.copy())

    # ------------------------------------------------------------------
    # Update methods
    # ------------------------------------------------------------------

    def _on_timestep_change(self, ts):
        if not self._dataset.ds.isopen():
            return

        if self._plot_type == 'Particle Animation':
            self._advect_particles(ts)
            self._render_particles()
            return

        if self._plot_type == 'Side-by-Side':
            self._render_side_by_side()
        elif self._plot_type == 'Vector Field':
            self._render_vector_field()
        elif self._plot_type == 'Magnitude':
            self._render_magnitude()
        elif self._plot_type == 'Vorticity':
            self._render_vorticity()
        elif self._plot_type == 'Streamlines':
            self._render_streamlines()
        self._canvas.draw_idle()

    def _on_colormap_change(self, cmap_name):
        for im in self._images:
            if im is not None:
                im.set_cmap(cmap_name)
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        import warnings
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                self._fig.tight_layout()
            self._canvas.draw_idle()
        except Exception:
            pass

    def closeEvent(self, event):
        if self._anim_controls:
            self._anim_controls.stop()
        self.closed.emit(self._plot_id)
        super().closeEvent(event)
