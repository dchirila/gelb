"""
Progress monitor for GeLB simulations.

Polls a NetCDF output file to track simulation progress and displays
a terminal progress bar with elapsed time and ETA.

Usage (from gelb-run):
    python -m gelb.visualization.progress_monitor <nc_file> <total_records> <pid>
"""

import os
import sys
import time

# HDF5 (and so netCDF-4) refuses by default to open a file for
# reading while another process has it open for writing: a POSIX
# file-lock is taken on nf90_create and released on nf90_close.
# Disable that lock from the *reader* side so the monitor can peek
# at header metadata while the simulation is still running. Safe
# because we only read statically-defined dims / var shapes /
# dtypes -- nothing that changes between nf90_enddef and
# nf90_close. MUST be set before `netCDF4` is imported.
os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")


def _format_time(seconds):
    """Format seconds as H:MM:SS or M:SS."""
    seconds = int(seconds)
    if seconds < 3600:
        return f'{seconds // 60}:{seconds % 60:02d}'
    return f'{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}'


def _progress_bar(fraction, width=40):
    """Render a progress bar string."""
    filled = int(width * fraction)
    bar = '\u2588' * filled + '\u2591' * (width - filled)
    return f'[{bar}]'


def _get_record_count(nc_path):
    """Get the number of time records written so far.

    Opens the file in read mode each time to get a fresh view of the
    unlimited time dimension.

    Caveat: for NetCDF-4 / HDF5 files the reader's view of the
    time-dim length does not update until the writer closes the
    file -- on HDF5 this is a file-locking side-effect that
    NF90_SHARE doesn't work around. The fallback calibration in
    `_compute_bytes_per_record()` + file-size tracking handles that
    case.
    """
    try:
        import netCDF4 as nc
        ds = nc.Dataset(nc_path, 'r')
        try:
            n = len(ds.dimensions['time'])
        finally:
            ds.close()
        return n
    except Exception:
        return -1


def _compute_bytes_per_record(nc_path):
    """Estimate bytes per time record from the NetCDF header.

    NetCDF metadata (dimensions and variable shapes/types) is
    written once at file creation, before the time loop starts, so
    it is visible even when the reader's view of the unlimited
    time-dim length isn't updating during the run. Sum, over all
    time-dependent variables, of (product of non-time dim sizes) *
    (itemsize of dtype); that gives the per-record payload size to
    within a few kilobytes of metadata overhead.
    """
    try:
        import netCDF4 as nc
        ds = nc.Dataset(nc_path, 'r')
        try:
            time_dims = {name for name, dim in ds.dimensions.items()
                         if dim.isunlimited()}
            total = 0
            for var in ds.variables.values():
                if not any(d in time_dims for d in var.dimensions):
                    continue   # static variable -- doesn't scale with time
                size = var.dtype.itemsize
                for d_name in var.dimensions:
                    if d_name in time_dims:
                        continue
                    size *= len(ds.dimensions[d_name])
                total += size
        finally:
            ds.close()
        return total if total > 0 else None
    except Exception:
        return None


def _get_file_size(nc_path):
    """Get the current file size in bytes."""
    try:
        return os.path.getsize(nc_path)
    except OSError:
        return 0


def _format_size(nbytes):
    """Format bytes as human-readable size."""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if nbytes < 1024:
            return f'{nbytes:.1f} {unit}'
        nbytes /= 1024
    return f'{nbytes:.1f} TB'


def _process_alive(pid):
    """Check if a process is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def monitor(nc_path, total_records, pid):
    """Poll the NetCDF file and display progress until the process exits.

    Short runs (<= ~2 s) are where the progress bar used to feel
    dishonest -- the monitor's own startup cost was eating most of
    the runtime, so the first poll typically saw the process
    already dead and snapped the bar straight from 0% to 100%.
    The fixes here: a tight poll cadence and an immediate first
    observation (no pre-sleep), plus a distinct code path for the
    "monitor attached after the sim already finished" case so we
    don't pretend we tracked progress we couldn't see.
    """
    start_time = time.monotonic()
    existence_poll_interval = 0.1   # while waiting for the NC file
    poll_interval            = 0.15  # once the simulation is writing

    # Wait for the file to appear. If the process exits while we're
    # waiting, the sim was too fast for us to see any record -- print
    # a single honest summary line and bail out rather than faking a
    # bar.
    while not os.path.exists(nc_path):
        if not _process_alive(pid):
            elapsed = time.monotonic() - start_time
            sys.stderr.write(
                f'\rSimulation completed in {_format_time(elapsed)} '
                f'(too fast to track incrementally).\n')
            sys.stderr.flush()
            return
        time.sleep(existence_poll_interval)

    # Try to read per-record size from the NetCDF header once.
    # This is the primary fallback for HDF5-backed outputs where
    # the reader never sees the time-dim length grow during the
    # simulation. If the header read fails on the first try (e.g.
    # the writer hasn't called nf90_enddef yet), we'll retry on
    # each poll until it succeeds.
    bytes_per_record = _compute_bytes_per_record(nc_path)

    # Loop structure: display BEFORE sleeping, so we always produce at
    # least one frame when the file exists (the previous code slept
    # first, which meant very short runs could exit without any
    # intermediate progress frame ever being rendered).
    while True:
        alive = _process_alive(pid)
        size = _get_file_size(nc_path)
        count = _get_record_count(nc_path)
        elapsed = time.monotonic() - start_time

        # Retry the header-based calibration if the first attempt
        # missed (e.g. we polled before nf90_enddef landed).
        if bytes_per_record is None:
            bytes_per_record = _compute_bytes_per_record(nc_path)

        # Prefer record count when the reader can actually see it.
        # For HDF5-backed outputs it typically stays at 0 until the
        # writer closes the file; the size-based fallback covers
        # that case using the bytes_per_record estimate from the
        # NetCDF header.
        if count > 0:
            # If we somehow have both a real count and a header-
            # derived estimate, prefer re-calibrating from the
            # observed ratio -- it picks up any metadata overhead
            # the header estimate missed.
            if count > 1 and bytes_per_record is None:
                bytes_per_record = size / count
            fraction = min(count / total_records, 1.0)
        elif bytes_per_record is not None and bytes_per_record > 0:
            estimated_count = int(size / bytes_per_record)
            fraction = min(estimated_count / total_records, 1.0)
            count = estimated_count
        else:
            fraction = 0
            count = 0

        pct = fraction * 100

        # If the Fortran process has finished, render a single
        # terminating frame (with `\n`) and exit. We skip the
        # intermediate in-place frame in this case -- otherwise we
        # would emit two bars back-to-back (one without a newline,
        # one with), and anything the simulation wrote to stdout
        # while dying (e.g. the MLUPS report) would land between
        # them and break the `\r`-based in-place overwrite.
        if not alive:
            # Re-read record count in case the sim wrote a final
            # batch between our pre-poll and here.
            count_final = _get_record_count(nc_path)
            if count_final >= 0:
                count = count_final
            if count <= 0 and total_records > 0:
                count = total_records
            size = _get_file_size(nc_path)
            elapsed = time.monotonic() - start_time
            fraction = (min(count / total_records, 1.0)
                        if total_records > 0 else 1.0)
            bar = _progress_bar(fraction)
            status = (
                f'\r{bar} {fraction * 100:5.1f}%  '
                f'{count}/{total_records} records  '
                f'{_format_size(size)}  '
                f'elapsed {_format_time(elapsed)}  '
                f'done'
            )
            sys.stderr.write(f'{status:<100}\n')
            sys.stderr.flush()
            break

        # ETA for in-flight display
        if fraction > 0.01 and fraction < 1.0:
            eta = elapsed / fraction * (1 - fraction)
            eta_str = f'ETA {_format_time(eta)}'
        elif fraction >= 1.0:
            eta_str = 'done'
        else:
            eta_str = 'ETA --:--'

        bar = _progress_bar(fraction)
        status = (
            f'\r{bar} {pct:5.1f}%  '
            f'{count}/{total_records} records  '
            f'{_format_size(size)}  '
            f'elapsed {_format_time(elapsed)}  '
            f'{eta_str}'
        )
        sys.stderr.write(f'{status:<100}')
        sys.stderr.flush()

        # Sleep AFTER the display so the first frame always paints.
        time.sleep(poll_interval)


def main():
    if len(sys.argv) != 4:
        print(f'Usage: {sys.argv[0]} <nc_file> <total_records> <pid>',
              file=sys.stderr)
        sys.exit(1)

    nc_path = sys.argv[1]
    total_records = int(sys.argv[2])
    pid = int(sys.argv[3])
    monitor(nc_path, total_records, pid)


if __name__ == '__main__':
    main()
