"""The installed commands work without uv and without a checkout.

``gelbc --version`` prints the package version; the ``gelb-run`` entry
point names its own interpreter in ``GELB_PYTHON`` before starting the
runner script, so a pip installation needs neither ``uv`` nor
``GELB_PYTHON`` set by hand; and a tree without the Highway sources
(a pip installation) refuses ``cpu_highway`` with one line that names
``-b cpu_fortran_serial`` (user manual, chapter 2 and chapter 16).
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys

from click.testing import CliRunner
import pytest

import gelb
from gelb import run_cli
from gelb.gelbc import cli

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / 'examples/basic/1d/ex0_int_vec_setto_one.gelb'


def test_gelbc_version():
    result = CliRunner().invoke(cli, ['--version'])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == f'gelbc {gelb.__version__}'


@pytest.mark.parametrize('preset', [None, '/some/other/python'])
def test_gelb_run_entry_point_names_its_interpreter(monkeypatch, preset):
    calls = []
    monkeypatch.setattr(run_cli.os, 'execv', lambda path, argv: calls.append((path, argv)))
    monkeypatch.setattr(sys, 'argv', ['gelb-run', '-n', '3', 'prog.gelb'])
    if preset is None:
        monkeypatch.delenv('GELB_PYTHON', raising=False)
    else:
        monkeypatch.setenv('GELB_PYTHON', preset)
    run_cli.main()
    assert calls == [(str(run_cli.SCRIPT), [str(run_cli.SCRIPT), '-n', '3', 'prog.gelb'])]
    assert os.environ['GELB_PYTHON'] == (preset or sys.executable)


def test_tree_without_highway_names_the_fortran_backend(tmp_path):
    """A copy of the runner in a tree with no pyproject.toml and no
    third_party/ stands in for a pip installation."""
    scripts = tmp_path / 'gelb' / 'scripts'
    scripts.mkdir(parents=True)
    shutil.copy(ROOT / 'gelb/scripts/gelb-run', scripts / 'gelb-run')
    result = subprocess.run(
        [str(scripts / 'gelb-run'), '-b', 'cpu_highway', '-n', '1', str(EXAMPLE)],
        cwd=tmp_path, env=dict(os.environ, GELB_PYTHON=sys.executable),
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 1
    assert 'this installation has no Highway' in result.stderr
    assert '-b cpu_fortran_serial' in result.stderr
    assert 'submodule' not in result.stderr
