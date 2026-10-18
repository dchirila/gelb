"""Shared compiler/runner flags and human-readable compilation descriptions."""
import json
from pathlib import Path

from click.testing import CliRunner

from gelb.gelbc import cli


ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / 'examples/basic/1d/ex0_int_vec_setto_one.gelb'


def test_short_options_match_long_options(tmp_path):
    short_path = tmp_path / 'short.f90'
    long_path = tmp_path / 'long.f90'
    short = CliRunner().invoke(cli, [str(EXAMPLE), '-b', 'cpu_fortran_serial',
        '-n', '10', '-w', '2', '-m', 'stdout', '-s', '42', '-o', str(short_path)])
    long = CliRunner().invoke(cli, [str(EXAMPLE), '--backend', 'cpu_fortran_serial',
        '--num-timesteps', '10', '--write-every', '2', '--output-mode', 'stdout',
        '--seed', '42', '--output', str(long_path)])
    assert short.exit_code == long.exit_code == 0, short.output + long.output
    assert short_path.read_text() == long_path.read_text()
    assert CliRunner().invoke(cli, ['-h']).exit_code == 0


def test_description_precedes_warnings(tmp_path):
    result = CliRunner().invoke(cli, [str(EXAMPLE), '-o', str(tmp_path / 'out.cpp')])
    assert result.exit_code == 0, result.output
    assert result.stderr.startswith('Simulation: "Pretty much the hello world of GeLB"\n')
    assert result.stderr.index('Simulation:') < result.stderr.index('[Warning]')
    assert 'Simulation:' not in result.stdout


def test_description_does_not_pollute_json_or_reports():
    result = CliRunner().invoke(cli, [str(EXAMPLE), '--diagnostics-json'])
    assert result.exit_code == 0
    assert json.loads(result.stdout)['diagnostics']
    assert result.stderr == ''
    result = CliRunner().invoke(cli, [str(EXAMPLE), '--stencils'])
    assert result.exit_code == 0, result.output
    assert 'Simulation:' not in result.output
