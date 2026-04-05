"""
Reusable control widgets for plot panels.
"""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSlider, QLabel,
    QComboBox, QSpinBox, QPushButton,
)


class TimestepSlider(QWidget):
    """Slider for selecting a timestep."""

    timestep_changed = Signal(int)

    def __init__(self, n_timesteps, parent=None):
        super().__init__(parent)
        self._n = n_timesteps

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel('t:'))

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, max(0, n_timesteps - 1))
        self._slider.setValue(n_timesteps - 1)
        self._slider.valueChanged.connect(self._on_change)
        layout.addWidget(self._slider)

        self._label = QLabel(str(n_timesteps - 1))
        self._label.setMinimumWidth(40)
        layout.addWidget(self._label)

    def _on_change(self, value):
        self._label.setText(str(value))
        self.timestep_changed.emit(value)

    def value(self):
        return self._slider.value()


class ColormapSelector(QWidget):
    """Dropdown for matplotlib colormaps."""

    colormap_changed = Signal(str)

    _COLORMAPS = [
        'viridis', 'plasma', 'inferno', 'magma', 'cividis',
        'coolwarm', 'RdBu_r', 'seismic',
        'hot', 'jet', 'gray',
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel('cmap:'))
        self._combo = QComboBox()
        self._combo.addItems(self._COLORMAPS)
        self._combo.currentTextChanged.connect(self.colormap_changed.emit)
        layout.addWidget(self._combo)

    def value(self):
        return self._combo.currentText()


class SliceControls(QWidget):
    """Axis and index selector for 3D slicing."""

    slice_changed = Signal(str, int)  # axis, index

    def __init__(self, shape_dict, parent=None):
        """
        Parameters
        ----------
        shape_dict : dict
            Mapping axis name -> size, e.g. {'x': 64, 'y': 64, 'z': 64}.
        """
        super().__init__(parent)
        self._shape = shape_dict

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel('slice:'))

        self._axis_combo = QComboBox()
        self._axis_combo.addItems(list(shape_dict.keys()))
        self._axis_combo.setCurrentText('z')
        self._axis_combo.currentTextChanged.connect(self._on_axis_change)
        layout.addWidget(self._axis_combo)

        layout.addWidget(QLabel('='))
        self._index_spin = QSpinBox()
        self._update_index_range()
        self._index_spin.valueChanged.connect(self._on_change)
        layout.addWidget(self._index_spin)

    def _update_index_range(self):
        axis = self._axis_combo.currentText()
        n = self._shape.get(axis, 1)
        self._index_spin.setRange(0, n - 1)
        self._index_spin.setValue(n // 2)

    def _on_axis_change(self, axis):
        self._update_index_range()
        self._on_change()

    def _on_change(self):
        self.slice_changed.emit(
            self._axis_combo.currentText(), self._index_spin.value())

    def axis(self):
        return self._axis_combo.currentText()

    def index(self):
        return self._index_spin.value()


class AnimationControls(QWidget):
    """Play/Pause button, FPS spinner, and frame slider for animation."""

    frame_tick = Signal(int)  # current frame index

    def __init__(self, n_frames, parent=None):
        super().__init__(parent)
        self._n_frames = n_frames
        self._current_frame = 0
        self._updating_slider = False  # guard against re-entrant updates

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Top row: play/pause + FPS
        top_row = QHBoxLayout()

        self._play_btn = QPushButton('Play')
        self._play_btn.setCheckable(True)
        self._play_btn.toggled.connect(self._on_toggle)
        top_row.addWidget(self._play_btn)

        top_row.addWidget(QLabel('FPS:'))
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 240)
        self._fps_spin.setValue(10)
        self._fps_spin.valueChanged.connect(self._update_timer_interval)
        top_row.addWidget(self._fps_spin)

        main_layout.addLayout(top_row)

        # Bottom row: frame slider
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(QLabel('t:'))

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, max(0, n_frames - 1))
        self._slider.setValue(0)
        self._slider.valueChanged.connect(self._on_slider_changed)
        bottom_row.addWidget(self._slider, stretch=1)

        self._frame_label = QLabel('0')
        self._frame_label.setMinimumWidth(40)
        bottom_row.addWidget(self._frame_label)

        main_layout.addLayout(bottom_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._update_timer_interval()

    def _update_timer_interval(self):
        self._timer.setInterval(1000 // self._fps_spin.value())

    def _on_toggle(self, playing):
        self._play_btn.setText('Pause' if playing else 'Play')
        if playing:
            self._timer.start()
        else:
            self._timer.stop()

    def _on_slider_changed(self, value):
        if self._updating_slider:
            return
        self._current_frame = value
        self._frame_label.setText(str(value))
        self.frame_tick.emit(value)

    def _advance(self):
        self._current_frame = (self._current_frame + 1) % self._n_frames
        self._updating_slider = True
        self._slider.setValue(self._current_frame)
        self._updating_slider = False
        self._frame_label.setText(str(self._current_frame))
        self.frame_tick.emit(self._current_frame)

    def stop(self):
        self._timer.stop()
        self._play_btn.setChecked(False)
