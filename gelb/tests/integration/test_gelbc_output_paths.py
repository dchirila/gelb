"""gelbc never overwrites the program it compiles.

``-o`` and ``--nc-output`` reject a name ending in ``.gelb`` and a path
that is the input file, before any code is generated; the program stays
as it was (user manual, chapter 2, "Compiling by hand"). An alias that
resolves only at run time is not detected, and gelbc does not claim it.
"""
from pathlib import Path
import shutil

from click.testing import CliRunner
import pytest

from gelb.gelbc import cli

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / 'examples/basic/1d/ex0_int_vec_setto_one.gelb'


@pytest.fixture
def program(tmp_path):
    path = tmp_path / 'prog.gelb'
    shutil.copy(EXAMPLE, path)
    return path


@pytest.mark.parametrize('option', ['-o', '--nc-output'])
@pytest.mark.parametrize('target', ['prog.gelb', 'other.gelb', 'sub/../prog.gelb'])
def test_an_output_that_would_be_the_program_is_rejected(tmp_path, program, option, target):
    (tmp_path / 'other.gelb').write_text('// another program\n')
    before = program.read_text()
    result = CliRunner().invoke(
        cli, [str(program), '-b', 'cpu_fortran_serial', option, str(tmp_path / target)])
    assert result.exit_code == 2
    assert option in result.output
    assert 'ends in .gelb' in result.output
    assert program.read_text() == before
    assert (tmp_path / 'other.gelb').read_text() == '// another program\n'


def test_the_input_under_another_name_is_rejected(tmp_path, program):
    alias = tmp_path / 'alias.f90'
    alias.symlink_to(program)
    before = program.read_text()
    result = CliRunner().invoke(
        cli, [str(program), '-b', 'cpu_fortran_serial', '-o', str(alias)])
    assert result.exit_code == 2
    assert 'is the input program' in result.output
    assert program.read_text() == before


def test_an_ordinary_output_is_written(tmp_path, program):
    out = tmp_path / 'prog.f90'
    result = CliRunner().invoke(
        cli, [str(program), '-b', 'cpu_fortran_serial', '-o', str(out),
              '--nc-output', 'result.nc'])
    assert result.exit_code == 0, result.output
    assert f'Generated: {out}' in result.output
    assert "'result.nc'" in out.read_text()
