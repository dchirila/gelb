"""A diagnostic on a ``-D`` value is a diagnostic, not a crash.

The override literal stands where the declared value stood, so an error
it causes (a division by the overridden constant, a grid size of 0)
points at the declaration line in text mode and carries that range in
``--diagnostics-json`` (user manual, chapter 3, "Command-line
constants"). Text mode runs in a subprocess: under pytest and in JSON
mode the exceptions take another path, which never showed the crash.
"""
import os
from pathlib import Path
import json
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]

CASES = [
    ('examples/lbm/3d/taylor_green_vortex_3d_bgk.gelb', 'N=0',
     'Division by zero', 'const int N = 32;'),
    ('examples/basic/1d/ex30_simple_constants_test.gelb', 'SIZE=0',
     'Grid size 0 is invalid', 'const int SIZE = 16;'),
]


def gelbc(tmp_path, *args):
    # Without pytest's variables in the environment, so that the child
    # takes the terminal path (print [Problem]/[Hint], exit 1).
    env = {k: v for k, v in os.environ.items() if not k.startswith('PYTEST')}
    return subprocess.run(
        [sys.executable, '-P', '-m', 'gelb.gelbc', *args, '-o', str(tmp_path / 'out.cpp')],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize(('example', 'define', 'problem', 'declaration'), CASES)
def test_text_mode_shows_the_problem_at_the_declaration(tmp_path, example, define, problem, declaration):
    result = gelbc(tmp_path, str(ROOT / example), '-D', define)
    output = result.stdout + result.stderr
    assert result.returncode == 1
    assert f'[Problem] {problem}' in output
    assert declaration in output
    assert 'AttributeError' not in output and 'Traceback' not in output
    assert not (tmp_path / 'out.cpp').exists()


@pytest.mark.parametrize(('example', 'define', 'problem', 'declaration'), CASES)
def test_json_mode_carries_the_declaration_range(tmp_path, example, define, problem, declaration):
    result = gelbc(tmp_path, str(ROOT / example), '-D', define, '--diagnostics-json')
    assert result.returncode == 1, result.stderr
    [diagnostic] = json.loads(result.stdout)['diagnostics']
    assert diagnostic['severity'] == 'error'
    assert problem in diagnostic['message']
    source_lines = (ROOT / example).read_text().splitlines()
    assert declaration in source_lines[diagnostic['range']['startLine']]
