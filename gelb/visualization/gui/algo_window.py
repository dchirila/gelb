"""
Interactive algorithm/stencil visualization window for gelb-view algo.

Displays the full lattice grid with stencil overlays. Users can select
a grid position (via sliders) and a block (via combo box) to see which
DFs are read/written and from which neighbor offsets.
"""

import signal
import sys

import matplotlib
matplotlib.use('QtAgg')

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)
from matplotlib.lines import Line2D
import numpy as np

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gelb.midware.stencil import ProgramStencils
from gelb.visualization.algo_viewer import (
    _get_velocity,
    _get_all_velocities,
)


class AlgoWindow(QMainWindow):
    """Interactive stencil visualization window."""

    def __init__(self, stencils: ProgramStencils,
                 block_names: list[str] | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("gelb-view algo")
        self.resize(1100, 750)

        self._stencils = stencils
        self._block_names = block_names or list(stencils.blocks.keys())

        # Determine lattice properties
        self._lattice_meta = next(iter(stencils.lattices.values()), None)
        self._ndim = self._lattice_meta.d if self._lattice_meta else 2
        self._q = self._lattice_meta.q if self._lattice_meta else 9
        self._grid_size = self._lattice_meta.grid_size if self._lattice_meta else None

        # Fallback grid size
        if self._grid_size is None:
            self._grid_size = tuple(32 for _ in range(self._ndim))

        # Current selection
        self._pos = [0] * self._ndim
        self._current_block = self._block_names[0] if self._block_names else None

        self._setup_ui()
        self._update_plot()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: canvas + toolbar + sliders
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self._fig, self._ax = plt.subplots(figsize=(7, 6))
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._toolbar = NavigationToolbar2QT(self._canvas, left)

        left_layout.addWidget(self._toolbar)
        left_layout.addWidget(self._canvas, stretch=1)

        # Position sliders
        slider_box = QGroupBox("Node position")
        slider_layout = QVBoxLayout(slider_box)
        self._sliders = []
        self._slider_labels = []
        dim_names = ["x", "y", "z"]
        for dim in range(self._ndim):
            row = QHBoxLayout()
            name = dim_names[dim] if dim < 3 else f"d{dim}"
            max_val = self._grid_size[dim] - 1
            label = QLabel(f"{name} = 0")
            label.setMinimumWidth(60)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, max_val)
            slider.setValue(0)
            slider.valueChanged.connect(self._on_slider_changed)
            row.addWidget(label)
            row.addWidget(slider, stretch=1)
            slider_layout.addLayout(row)
            self._sliders.append(slider)
            self._slider_labels.append((label, name))

        left_layout.addWidget(slider_box)

        # Right: side panel
        right = QWidget()
        right.setMinimumWidth(200)
        right.setMaximumWidth(300)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)

        # Node class display
        nc_box = QGroupBox("Node class")
        nc_layout = QVBoxLayout(nc_box)
        self._nc_label = QLabel("—")
        self._nc_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        nc_layout.addWidget(self._nc_label)
        right_layout.addWidget(nc_box)

        # Block selector
        block_box = QGroupBox("Block")
        block_layout = QVBoxLayout(block_box)
        self._block_combo = QComboBox()
        self._block_combo.addItems(self._block_names)
        self._block_combo.currentTextChanged.connect(self._on_block_changed)
        block_layout.addWidget(self._block_combo)

        # Block type label
        self._block_type_label = QLabel("")
        self._block_type_label.setStyleSheet("color: gray;")
        block_layout.addWidget(self._block_type_label)
        right_layout.addWidget(block_box)

        # Stencil info
        info_box = QGroupBox("Stencil info")
        info_layout = QVBoxLayout(info_box)
        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)
        info_layout.addWidget(self._info_label)
        right_layout.addWidget(info_box)

        # Legend
        legend_box = QGroupBox("Legend")
        legend_layout = QVBoxLayout(legend_box)
        for color, style, text in [
            ("#d0d0d0", "filled", "DF (inactive)"),
            ("royalblue", "filled", "Input (f.in)"),
            ("green", "ring", "Output (f.out)"),
        ]:
            row = QHBoxLayout()
            dot = QLabel()
            if style == "ring":
                dot.setStyleSheet(
                    f"background: white; border: 2px solid {color}; "
                    "border-radius: 6px; min-width: 12px; max-width: 12px; "
                    "min-height: 12px; max-height: 12px;"
                )
            else:
                dot.setStyleSheet(
                    f"background: {color}; border-radius: 6px; "
                    "min-width: 12px; max-width: 12px; "
                    "min-height: 12px; max-height: 12px;"
                )
            row.addWidget(dot)
            row.addWidget(QLabel(text), stretch=1)
            legend_layout.addLayout(row)
        right_layout.addWidget(legend_box)

        right_layout.addStretch()

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_slider_changed(self):
        dim_names = ["x", "y", "z"]
        for dim in range(self._ndim):
            val = self._sliders[dim].value()
            self._pos[dim] = val
            label, name = self._slider_labels[dim]
            label.setText(f"{name} = {val}")
        self._update_side_panel()

    def _on_block_changed(self, block_name: str):
        self._current_block = block_name
        self._update_plot()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _update_side_panel(self):
        # Node class at current position
        nc = self._stencils.get_node_class_at(*self._pos)
        self._nc_label.setText(nc if nc else "—")

        # Update block combo to show blocks for this node class
        if nc and nc in self._stencils.node_classes:
            nci = self._stencils.node_classes[nc]
            associated = [nci.initializer, nci.dynamic, nci.gauge]
            # Bold the associated blocks' text via tooltip
            self._block_type_label.setText(
                f"Node class blocks: {', '.join(associated)}"
            )
        else:
            self._block_type_label.setText("")

    def _update_plot(self):
        self._update_side_panel()

        ax = self._ax
        ax.clear()

        if self._current_block not in self._stencils.blocks:
            self._canvas.draw_idle()
            return

        bs = self._stencils.blocks[self._current_block]

        # Update info label
        n_reads = len(bs.reads)
        n_writes = len(bs.writes)
        locality = "local" if bs.is_local else "non-local"
        self._info_label.setText(
            f"Reads: {n_reads}  |  Writes: {n_writes}\n"
            f"Neighborhood: {locality}\n"
            f"Read offsets: {len(bs.read_offsets)}  |  "
            f"Write offsets: {len(bs.write_offsets)}"
        )

        if self._ndim == 1:
            self._render_1d(ax, bs)
        else:
            self._render_2d(ax, bs)

        ax.set_title(f"{self._current_block} ({bs.block_type})", fontsize=11)
        self._fig.tight_layout()
        self._canvas.draw_idle()

    def _render_1d(self, ax, bs):
        all_offsets = bs.read_offsets | bs.write_offsets
        if not all_offsets:
            return

        min_x = min(o[0] for o in all_offsets) - 1
        max_x = max(o[0] for o in all_offsets) + 1
        velocities = _get_all_velocities(1)
        scale = 0.25

        # Draw nodes and gray DFs
        for x in range(min_x, max_x + 1):
            ax.plot(x, 0, "o", color="lightgray", markersize=14, zorder=1)
            for df_idx, vel in velocities.items():
                cx = x + scale * vel[0]
                ax.plot(cx, 0, "o", color="#d0d0d0", markersize=8, zorder=2)

        # Center node
        ax.plot(0, 0, "s", color="black", markersize=16, zorder=3,
                fillstyle="none", linewidth=2)

        read_keys = {(a.spatial_offsets, a.df_index) for a in bs.reads}

        # Reads (filled blue)
        for a in bs.reads:
            vel = _get_velocity(a.df_index, 1)
            cx = a.spatial_offsets[0] + scale * vel[0]
            ax.plot(cx, 0, "o", color="royalblue", markersize=8, zorder=4)
            label = "*" if a.df_index is None else str(a.df_index)
            ax.annotate(label, (cx, 0), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=8,
                        color="royalblue")

        # Writes (unfilled green)
        for a in bs.writes:
            vel = _get_velocity(a.df_index, 1)
            cx = a.spatial_offsets[0] + scale * vel[0]
            ax.plot(cx, 0, "o", color="green", markersize=11, zorder=5,
                    fillstyle="none", markeredgewidth=2)
            label = "*" if a.df_index is None else str(a.df_index)
            if (a.spatial_offsets, a.df_index) not in read_keys:
                ax.annotate(label, (cx, 0), textcoords="offset points",
                            xytext=(0, 10), ha="center", fontsize=8,
                            color="green")

        ax.set_xlim(min_x - 0.5, max_x + 0.5)
        ax.set_ylim(-0.8, 0.8)
        ax.set_aspect("equal")
        ax.axhline(0, color="lightgray", linewidth=0.5, zorder=0)
        ax.set_yticks([])

    def _render_2d(self, ax, bs):
        all_offsets = bs.read_offsets | bs.write_offsets
        if not all_offsets:
            return

        min_x = min(o[0] for o in all_offsets) - 1
        max_x = max(o[0] for o in all_offsets) + 1
        min_y = min(o[1] for o in all_offsets) - 1
        max_y = max(o[1] for o in all_offsets) + 1
        velocities = _get_all_velocities(2)
        scale = 0.2

        # Draw grid nodes and gray DFs
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                ax.plot(x, y, "o", color="lightgray", markersize=12, zorder=1)
                for df_idx, vel in velocities.items():
                    cx = x + scale * vel[0]
                    cy = y + scale * vel[1]
                    ax.plot(cx, cy, "o", color="#d0d0d0", markersize=5,
                            zorder=2)

        # Center node
        ax.plot(0, 0, "s", color="black", markersize=16, zorder=3,
                fillstyle="none", linewidth=2)

        read_keys = {(a.spatial_offsets, a.df_index) for a in bs.reads}

        # Reads (filled blue)
        for a in bs.reads:
            ox, oy = a.spatial_offsets
            vel = _get_velocity(a.df_index, 2)
            cx = ox + scale * vel[0]
            cy = oy + scale * vel[1]
            ax.plot(cx, cy, "o", color="royalblue", markersize=7, zorder=4)
            label = "*" if a.df_index is None else str(a.df_index)
            ax.annotate(label, (cx, cy), textcoords="offset points",
                        xytext=(5, 5), ha="left", fontsize=7,
                        color="royalblue")

        # Writes (unfilled green)
        for a in bs.writes:
            ox, oy = a.spatial_offsets
            vel = _get_velocity(a.df_index, 2)
            cx = ox + scale * vel[0]
            cy = oy + scale * vel[1]
            ax.plot(cx, cy, "o", color="green", markersize=10, zorder=5,
                    fillstyle="none", markeredgewidth=1.5)
            label = "*" if a.df_index is None else str(a.df_index)
            if (a.spatial_offsets, a.df_index) not in read_keys:
                ax.annotate(label, (cx, cy), textcoords="offset points",
                            xytext=(5, 5), ha="left", fontsize=7,
                            color="green")

        ax.set_xlim(min_x - 0.5, max_x + 0.5)
        ax.set_ylim(min_y - 0.5, max_y + 0.5)
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.15)


def launch_algo_gui(stencils: ProgramStencils,
                    block_names: list[str] | None = None):
    """Create QApplication, show algo window, enter event loop."""
    app = QApplication.instance() or QApplication(sys.argv)
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # see gui/app.py
    window = AlgoWindow(stencils, block_names)
    window.show()
    sys.exit(app.exec())
