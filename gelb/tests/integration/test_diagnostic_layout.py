"""Exercise the real terminal path, including exceptions that exit immediately."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / 'gelb/tests/fixtures/regressions'


@pytest.mark.parametrize(('filename', 'anchor', 'message'), [
    ('write_in.gelb', 'in', 'Your GeLB program contains a syntax error.'),
    ('initializer_coverage.gelb', 'Init', "Initializer 'Init'"),
    ('paint_bounds.gelb', 'WALL', "Geometry paint to 'WALL'"),
    ('unknown_class.gelb', 'WALL_TYPO', 'You mention WALL_TYPO'),
])
def test_error_layout(filename, anchor, message, tmp_path):
    env = dict(os.environ)
    env.pop('PYTEST_CURRENT_TEST', None)
    result = subprocess.run(
        [sys.executable, '-m', 'gelb.gelbc', str(FIXTURES / filename),
         '--output', str(tmp_path / 'out.cpp')],
        env=env, text=True, capture_output=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith('[Problem]'))
    assert message in lines[index]
    assert lines[index - 1].strip() == '^^'
    source = lines[index - 2]
    # The block name (or offending token) is directly above the caret.
    col = lines[index - 1].index('^^')
    assert source[col:].startswith(anchor), (source, lines[index - 1])
    assert lines[index + 1].startswith('[Hint]')


def test_warning_layout_and_stream(tmp_path):
    result = subprocess.run(
        [sys.executable, '-m', 'gelb.gelbc',
         str(ROOT / 'examples/basic/1d/ex0_int_vec_setto_one.gelb'),
         '--output', str(tmp_path / 'out.cpp')],
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stderr.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith('[Warning]'))
    assert lines[index - 1].strip() == '^^'
    col = lines[index - 1].index('^^')
    assert lines[index - 2][col:].startswith('SetDFsToOne')
    assert lines[index + 1].startswith('[Hint]')
    assert '[Warning]' not in result.stdout


def test_last_source_line_without_newline(tmp_path):
    path = tmp_path / 'last_line.gelb'
    path.write_text((FIXTURES / 'unknown_class.gelb').read_text().rstrip('\n'))
    env = dict(os.environ)
    env.pop('PYTEST_CURRENT_TEST', None)
    result = subprocess.run([sys.executable, '-m', 'gelb.gelbc', str(path)],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith('[Problem]'))
    assert 'geometry { nodes[:] = WALL_TYPO; }' in lines[index - 2]
    assert lines[index - 1].strip() == '^^'
    assert lines[index + 1].startswith('[Hint] Define WALL_TYPO.')


def test_warning_anchors_the_named_declaration_on_a_shared_line(tmp_path):
    source = (FIXTURES / 'initializer_coverage.gelb').read_text()
    source = source.replace('f.out[x | 0] = 0.5;', 'f.out[x | :] = 0.5;')
    source = source.replace('16, false); }',
                            '16, false); lattice g(1, 3, real, 16, false); }')
    path = tmp_path / 'unused.gelb'
    path.write_text(source)
    result = subprocess.run([sys.executable, '-m', 'gelb.gelbc', str(path),
                             '-o', str(tmp_path / 'out.cpp')],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stderr.splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith('[Warning]'))
    col = lines[index - 1].index('^^')
    assert lines[index - 2][col:].startswith('g(')


def test_warning_without_available_source_keeps_its_message(monkeypatch, capsys):
    from gelb.utils import config
    from gelb.utils.output_to_terminal import warning_with_hint_to_term

    monkeypatch.setattr(config, 'GELB_SRC_RAW', '')
    monkeypatch.setattr(config, 'DIAGNOSTICS_MODE', False)
    warning_with_hint_to_term('A stored finding', 'Check the source', source_line=8)
    captured = capsys.readouterr()
    assert captured.out == ''
    assert captured.err == '[Warning] A stored finding\n[Hint] Check the source\n'


def test_redefinition_keeps_messages_with_the_second_source_location(tmp_path):
    source = (FIXTURES / 'unknown_class.gelb').read_text()
    source = source.replace('lattices {',
        'global_constants { const int N = 16; const int N = 32; }\nlattices {')
    path = tmp_path / 'redefinition.gelb'
    path.write_text(source)
    env = dict(os.environ)
    env.pop('PYTEST_CURRENT_TEST', None)
    result = subprocess.run([sys.executable, '-m', 'gelb.gelbc', str(path)],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 1
    lines = result.stdout.splitlines()
    problems = [i for i, line in enumerate(lines) if line.startswith('[Problem]')]
    assert len(problems) == 2
    assert all(lines[i - 1].strip() == '^^' for i in problems)
    assert 'Previous definiton of N' in lines[problems[0]]
    assert 'Re-definition of N here.' in lines[problems[1]]
    assert lines[problems[1] + 1].startswith('You define a constant definition named N.')
    assert lines[problems[1] + 2].startswith('[Hint] Rename (or remove)')
