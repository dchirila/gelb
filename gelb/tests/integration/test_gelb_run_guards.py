"""gelb-run reports success only for a run that happened.

``-n`` takes 0 to 2 147 483 646 and ``-w`` 1 to 2 147 483 647 (the
programs' step counters are 32-bit); a leading zero means decimal; any
other value is an error, and the previous run's ``.nc`` stays in place
(user manual, chapter 2, "Running a program"). ``gelbc`` applies the same
ranges. A program that exits with a nonzero status fails the run with
that status, its output shown; the previous ``.nc`` is removed only after
a successful build; a read-only ``.nc`` stops the run before anything is
generated; a gelbc option that writes no source is an error.

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
[[ "${FAKE_FC_RC:-0}" == 0 ]] || exit "$FAKE_FC_RC"
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


@pytest.mark.parametrize('n', ['1', '2'])
def test_a_failing_program_fails_the_run_and_shows_its_output(tmp_path, env, n):
    (tmp_path / NC).write_text('previous')
    env['FAKE_RC'] = '3'
    result = run(tmp_path, env, '-n', n)
    assert result.returncode == 3
    assert 'program says: 3' in result.stdout
    assert 'the simulation exited with status 3' in result.stderr
    assert f'it wrote no {NC}' in result.stderr
    assert not (tmp_path / NC).exists()


@pytest.mark.parametrize('failure', ['translation', 'build'])
def test_a_failed_translation_or_build_keeps_the_previous_result(tmp_path, env, failure):
    (tmp_path / NC).write_text('previous')
    args = ['-D', 'NO_SUCH_CONSTANT=1'] if failure == 'translation' else []
    if failure == 'build':
        env['FAKE_FC_RC'] = '1'
    result = run(tmp_path, env, '-n', '2', *args)
    assert result.returncode != 0
    assert 'the simulation exited' not in result.stderr
    assert (tmp_path / NC).read_text() == 'previous'


def test_a_read_only_result_stops_the_run_before_generating(tmp_path, env):
    (tmp_path / NC).write_text('previous')
    (tmp_path / NC).chmod(0o444)
    result = run(tmp_path, env, '-n', '2')
    assert result.returncode == 1
    assert f'{NC} is read-only' in result.stderr
    assert 'Translating' not in result.stderr + result.stdout
    assert (tmp_path / NC).read_text() == 'previous'


@pytest.mark.parametrize('keep', [[], ['-k']])
def test_a_report_only_gelbc_option_runs_nothing(tmp_path, env, keep):
    assert run(tmp_path, env, '-n', '2', *keep).returncode == 0
    env['GELBC_EXTRA'] = '--stencils'
    result = run(tmp_path, env, '-n', '2', *keep)
    assert result.returncode == 1
    assert 'no simulation ran' in result.stderr
