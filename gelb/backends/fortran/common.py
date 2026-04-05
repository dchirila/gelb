"""Shared Fortran code-generation helpers used by multiple backends.

Both the CPU-serial and the CUDA backends emit identical Fortran text for
certain boilerplate (MLUPS timing printouts, total-nodes expression, etc.).
Centralising the strings here ensures that any tweak to the user-visible
output (format specifiers, label wording, etc.) propagates to every
backend automatically.

Each helper takes an ``emit`` callable (typically the backend's
``self._emit``) and appends lines to the current source buffer.
"""

from typing import Callable, Iterable


def total_nodes_rhs(dim_size_fnames: Iterable[str]) -> str:
    """Return the Fortran RHS for ``gelb_total_nodes = ...``.

    Example: ``['nx', 'ny']`` -> ``'dble(nx) * dble(ny)'``.
    """
    return ' * '.join(f'dble({name})' for name in dim_size_fnames)


def emit_mlups_wall_time_calc(emit: Callable[[str], None]) -> None:
    """Emit ``call system_clock`` + ``gelb_wall_secs = ...`` (2 lines).

    Assumes ``gelb_clock_start``, ``gelb_clock_end``, ``gelb_clock_rate``
    and ``gelb_wall_secs`` have been declared by the caller.
    """
    emit('call system_clock(gelb_clock_end)')
    emit('gelb_wall_secs = dble(gelb_clock_end - gelb_clock_start) '
         '/ dble(gelb_clock_rate)')


def emit_mlups_report_header(emit: Callable[[str], None]) -> None:
    """Emit the ``=== MLUPS Report ===`` banner + the wall-time line."""
    emit(r"write(*, '(A)') '=== MLUPS Report ==='")
    emit(r"write(*, '(A,F10.3,A)') "
         r"'  Wall time:    ', gelb_wall_secs, ' s'")


def emit_mlups_throughput_lines(emit: Callable[[str], None],
                                num_timesteps,
                                dyn_secs_expr: str) -> None:
    """Emit the ``Real MLUPS`` and ``Compute MLUPS`` printouts.

    Args:
        emit: the backend's line-emit callable.
        num_timesteps: timestep count (stringifiable) used as the numerator.
        dyn_secs_expr: Fortran expression evaluating to the dynamic compute
            time in seconds (e.g. ``gelb_dyn_secs`` for the CPU backend or
            ``dble(gelb_dyn_ms_total) / 1000.0d0`` for the CUDA backend).
    """
    emit(f"write(*, '(A,F10.1,A)') "
         f"'  Real MLUPS:   ', "
         f"(gelb_total_nodes * dble({num_timesteps})) "
         f"/ (gelb_wall_secs * 1.0d6), ' MLUPS'")
    emit(f"write(*, '(A,F10.1,A)') "
         f"'  Compute MLUPS:', "
         f"(gelb_total_nodes * dble({num_timesteps})) "
         f"/ ({dyn_secs_expr} * 1.0d6), ' MLUPS'")
