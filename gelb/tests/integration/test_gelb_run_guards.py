"""gelb-run refuses bad step counts before it runs anything.

``-n`` takes 0 to 2 147 483 646 and ``-w`` 1 to 2 147 483 647 (the
programs' step counters are 32-bit); a leading zero means decimal; any
other value is an error, and the previous run's ``.nc`` stays in place
(user manual, chapter 2, "Running a program"). ``gelbc`` applies the same
ranges.

Toolchain-free: a stand-in ``GELB_FC`` writes a shell "program" that
prints one line and exits with ``$FAKE_RC``, so the tests need only bash,
Python and gelbc.
"""
import os
from pathlib import Path
import subprocess
import sys

from click.testing import CliRunner
import pytest

from gelb.gelbc import cli

ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / 'gelb/scripts/gelb-run'
PROGRAM = ROOT / 'examples/basic/1d/ex0_int_vec_setto_one.gelb'
NC = PROGRAM.with_suffix('.nc').name

FAKE_FC = """#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do [[ $1 == -o ]] && out=$2; shift; done
printf '#!/bin/sh\\necho "program says: %s"\\nexit %s\\n' "$FAKE_RC" "$FAKE_RC" > "$out"
chmod +x "$out"
"""


@pytest.fixture
def env(tmp_path):
    fc = tmp_path / 'fc'
    fc.write_text(FAKE_FC)
    fc.chmod(0o755)
    e = dict(os.environ, GELB_PYTHON=sys.executable, GELB_FC=str(fc),
             GELB_NETCDF_INC='-I/x', GELB_NETCDF_LIB='-L/x', FAKE_RC='0')
    e.pop('GELBC_EXTRA', None)
    return e


def run(cwd, env, *args):
    return subprocess.run(
        [str(RUNNER), '-b', 'cpu_fortran_serial', *args, str(PROGRAM)],
        cwd=cwd, env=env, text=True, capture_output=True, timeout=120)


@pytest.mark.parametrize('args', [
    ['-w', '0'], ['-w', '08x'], ['-w', '-1'], ['-n', '-1'], ['-n', 'ten'],
    ['-n', '2147483647'], ['-w', '2147483648'], ['-w', '18446744073709551617'],
])
def test_a_bad_count_fails_and_keeps_the_previous_result(tmp_path, env, args):
    (tmp_path / NC).write_text('previous')
    result = run(tmp_path, env, '-n', '5', *args)
    assert result.returncode != 0
    assert f'gelb-run: error: {args[0]} ' in result.stderr, result.stderr
    assert (tmp_path / NC).read_text() == 'previous'


def test_a_leading_zero_is_decimal(tmp_path, env):
    result = run(tmp_path, env, '-n', '08', '-w', '08')
    assert result.returncode == 0, result.stderr
    assert 'value too great' not in result.stderr
    assert 'program says: 0' in result.stdout


@pytest.mark.parametrize('args', [['-n', '-1'], ['-n', '2147483647'], ['-w', '0']])
def test_gelbc_rejects_the_same_counts(tmp_path, args):
    result = CliRunner().invoke(cli, [str(PROGRAM), '-o', str(tmp_path / 'out.f90'),
                                      '-b', 'cpu_fortran_serial', *args])
    assert result.exit_code == 2
    assert 'not in the range' in result.output
    assert not (tmp_path / 'out.f90').exists()
