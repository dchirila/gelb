"""Constants and selectors obey the compile-time rules of user manual chapter 3."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from gelb.compiler_pipeline import PipelineOptions, PipelineProfile, compile_source
from gelb.frontend import stage1_frontend as frontend
from gelb.gelb_ast import ASTNodes as A
from gelb.midware.stage2_midware import extract_stencils
from gelb.tests.test_utils import get_resolved_ast, get_typed_ast, minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBExStencilError, GeLBExTypeError


FUNCTIONS = """
function ID(int p) -> (int r) { r = p; }
function Rnd() -> (int r) { r = int(3.0 * random()); }
function Hop() -> (int r) { r = Rnd(); }
function TwoC() -> (int r) { const int k = 0; int a = k; r = a; }
"""


def compile_program(source, profile):
    return compile_source(source, profile, PipelineOptions(emit_warnings=False))


@pytest.mark.parametrize('profile', list(PipelineProfile))
@pytest.mark.parametrize('block', ['initializer', 'dynamic', 'gauge', 'function'])
@pytest.mark.parametrize('declaration, dependency', [
    ('int s = 2; const int k = s;', "'s'"),
    ('const real k = random();', 'random()'),
    ('const int k = Hop();', 'random()'),
])
def test_nonconstant_declarations_are_rejected_even_in_uncalled_functions(
        profile, block, declaration, dependency):
    functions = FUNCTIONS
    contents = {}
    if block == 'function':
        functions += f'function Unused(int p) -> (int r) {{ {declaration} r = 0; }}'
    else:
        tail = {'initializer': 'f.out[x | 0] = 0;',
                'dynamic': 'f.out[x | 0] = f.in[x | 0];',
                'gauge': 'val = f.in[x | 0];'}[block]
        contents[block + '_content'] = declaration + tail
    with pytest.raises(GeLBExTypeError) as error:
        compile_program(minimal_gelb_program_1d(**contents) + functions, profile)
    assert "Constant 'k' initializer must be compile-time evaluable" in error.value.error
    assert dependency in error.value.error
    assert error.value._source_location()[0] is not None


@pytest.mark.parametrize('profile', list(PipelineProfile))
@pytest.mark.parametrize('body, dependency', [
    ('const int k = p; r = k;', "'p'"),
    ('r = 0; const int k = r;', "'r'"),
])
def test_function_parameters_and_outputs_are_not_constants(profile, body, dependency):
    source = minimal_gelb_program_1d() + f'function F(int p) -> (int r) {{ {body} }}'
    with pytest.raises(GeLBExTypeError) as error:
        compile_program(source, profile)
    assert dependency in error.value.error


@pytest.mark.parametrize('profile', list(PipelineProfile))
@pytest.mark.parametrize('index, prefix, dependency', [
    ('mod(x, 1)', '', "'x'"), ('mod(t, 1)', '', "'t'"),
    ('k', 'int k = 0;', "'k'"), ('ID(k)', 'int k = 0;', "'k'"),
    ('ID(x)', '', "'x'"), ('Rnd()', '', 'random()'), ('Hop()', '', 'random()'),
    ('int(f.in[x | 0])', '', 'lattice access'),
    ('int(sum(upstream_dfs(f, x, EX)))', '', 'upstream_dfs()'),
    ('int(sum(bounce_back_dfs(f, x, EX)))', '', 'bounce_back_dfs()'),
    ('1 / 0', '', 'does not evaluate'),
])
@pytest.mark.parametrize('write', [False, True])
def test_df_selectors_are_constant_on_reads_and_writes(profile, index, prefix, dependency, write):
    selection = f'f.out[x | {index}] = 0;' if write else f'f.out[x | 0] = f.in[x | {index}];'
    source = minimal_gelb_program_1d(
        dynamic_content=prefix + selection,
        global_constants_content='const array[int, 3] EX = {0, 1, -1};').replace(
            'f(1, 1, int,', 'f(1, 3, int,') + FUNCTIONS
    with pytest.raises(GeLBExTypeError) as error:
        compile_program(source, profile)
    assert 'DF selector must be compile-time evaluable' in error.value.error
    assert dependency in error.value.error
    assert error.value._source_location()[0] is not None


@pytest.mark.parametrize('profile', list(PipelineProfile))
@pytest.mark.parametrize('index', ['ID(int(3.0 * random()))', 'Rnd()', 'Hop()'])
@pytest.mark.parametrize('write', [False, True])
def test_call_borne_draws_in_array_subscripts_are_rejected(profile, index, write):
    use = f'w[{index}] = 9;' if write else f'int a = w[{index}];'
    source = minimal_gelb_program_1d(dynamic_content=
        'array[int, 3] w = {1, 2, 3};' + use + 'f.out[x | 0] = 0;') + FUNCTIONS
    with pytest.raises(GeLBExTypeError, match='Array index must be compile-time evaluable'):
        compile_program(source, profile)


@pytest.mark.parametrize('profile', list(PipelineProfile))
def test_constants_calls_arrays_and_dimensions_remain_valid(profile):
    source = minimal_gelb_program_1d(
        global_constants_content='const array[int, 2] C = {0, 1};',
        initializer_content='const int a = Nx - 32; f.out[x | a] = 1;',
        dynamic_content='const int a = ID(0); const int b = a; '
                        'array[int, 2] w = {4, 5}; const array[int, 2] c = C[0:1]; '
                        'f.out[x | TwoC()] = w[ID(b)] + f.in[x | b] * t;',
        gauge_content='const int k = C[0]; val = f.in[x | k];') + FUNCTIONS
    result = compile_program(source, profile)
    assert result.pass_names.index('validate_static_selectors') == \
        result.pass_names.index('canonicalize_types') + 1


@pytest.mark.parametrize('parameter', ['x', 't'])
@pytest.mark.parametrize('profile', list(PipelineProfile))
def test_function_local_constants_work_in_df_bounds_and_geometry(profile, parameter):
    source = minimal_gelb_program_1d(
        dynamic_content='f.out[x | F(0)] = f.in[x | F(0)];',
        geometry_content='nodes[where x >= F(0)] = BULK;')
    source += f'function F(int {parameter}) -> (int r) {{ const int k = 0; r = k + {parameter}; }}'
    assert compile_program(source, profile).ast is not None


@pytest.mark.parametrize('functions', [
    'function R(int p) -> (int r) { r = R(p); }',
    'function R(int p) -> (int r) { r = S(p); } function S(int p) -> (int r) { r = R(p); }',
])
def test_analysis_constant_call_cycles_are_located_errors(functions):
    source = minimal_gelb_program_1d(gauge_content='const int k = R(1); val = k;') + functions
    with pytest.raises(GeLBExTypeError, match='recursive function') as error:
        compile_program(source, PipelineProfile.PROGRAM_ANALYSIS)
    assert error.value._source_location()[0] is not None


def test_a_deep_pre_type_expression_is_walked_without_python_recursion():
    ast = frontend.get_ast('gelb_program', minimal_gelb_program_1d(
        gauge_content='const int k = 1; val = k;'))
    frontend.build_symbols_tables(ast)
    stmt = ast.gauges[0].stmts[0]
    for _ in range(450):
        stmt.value = A.Add_N(stmt.code_range, stmt.value, A.IntLiteral_N(stmt.code_range, 1))
    assert frontend.validate_static_selectors(ast) is ast


@pytest.mark.parametrize('write', [False, True])
def test_midware_direct_entry_rejects_unresolved_df_bounds(write):
    selection = 'f.out[x | x] = 0;' if write else 'f.out[x | 0] = f.in[x | mod(x, 1)];'
    ast = get_typed_ast(minimal_gelb_program_1d(dynamic_content=selection))
    with pytest.raises(GeLBExStencilError, match='not a compile-time integer'):
        extract_stencils(ast)


@pytest.mark.parametrize('selector, message', [
    ('k:2', "'k'"), ('0:k', "'k'"), ('2:1', 'reversed'),
    ('-1', 'outside'), ('3', 'outside'), ('1.5', 'non-integer'),
])
def test_direct_validation_checks_both_bounds_integer_type_and_extent(selector, message):
    ast = get_resolved_ast(minimal_gelb_program_1d(dynamic_content=
        f'int k = 1; f.out[x | {selector}] = 0;').replace('f(1, 1, int,', 'f(1, 3, int,'))
    with pytest.raises(GeLBExTypeError, match=message):
        frontend.validate_static_selectors(ast)


def test_direct_validation_folds_calls_and_uses_typed_local_constant_bindings():
    ast = get_resolved_ast(minimal_gelb_program_1d(dynamic_content=
        'const int8 k = int8(256); const int j = k; f.out[x | ID(j):TwoC()] = 0;') + FUNCTIONS)
    frontend.validate_static_selectors(ast)
    bounds = ast.dynamics[0].stmts[-1].lhs.element_ranges[-1]
    assert isinstance(bounds.low, A.IntLiteral_N) and bounds.low.value == 0
    assert isinstance(bounds.high, A.IntLiteral_N) and bounds.high.value == 0


def test_synthesized_open_array_high_does_not_act_as_a_function_grid_reference():
    ast = get_resolved_ast(minimal_gelb_program_1d() +
        'function F(array[int, 3] w) -> (int r) { array[int, 3] a = w[:]; r = a[0]; }')
    assert frontend.validate_static_selectors(ast) is ast


@pytest.mark.parametrize('profile', ['codegen', 'diagnostics', 'analysis'])
@pytest.mark.parametrize('gauge, result, message', [
    ('val = f.in[x | F()];', 'int(random())',
     'DF selector must be compile-time evaluable; depends on random()'),
    ('val = f.in[x | F()];', 'a',
     'DF selector must be compile-time evaluable; depends on an index that does not evaluate'),
    ('const int k = F(); array[int, 2] w = {1, 2}; val = w[0] + k;', 'int(random())',
     "Constant 'k' initializer must be compile-time evaluable; depends on random()"),
    ('const int k = F(); val = f.in[x | k];', 'a',
     'DF selector must be compile-time evaluable; depends on an index that does not evaluate'),
])
def test_cli_speculative_evaluation_defers_to_selector_validation(tmp_path, profile, gauge, result, message):
    functions = ('function Two() -> (int a, int b) { a = 0; b = 1; }\n'
                 'function F() -> (int r) { int a; int b; {a, b} = Two(); r = ' + result + '; }')
    source = minimal_gelb_program_1d(gauge_content=gauge) + functions
    _check_cli_rejection(tmp_path, profile, source, gauge, message)


@pytest.mark.parametrize('profile', ['codegen', 'diagnostics', 'analysis'])
@pytest.mark.parametrize('gauge', [
    'val = f.in[x | Rr(1)];',
    'val = f.in[x | mod(Rr(1), 1)];',
    'const int k = Rr(1); array[int, 2] w = {1, 2}; val = w[0] + k;',
])
def test_cli_recursive_evaluation_is_a_located_rejection(tmp_path, profile, gauge):
    function = 'function Rr(int p) -> (int r) { r = Rr(p); }'
    source = minimal_gelb_program_1d(gauge_content=gauge) + function
    marker = gauge if profile == 'analysis' else function
    message = "recursive function 'Rr'" if profile == 'analysis' else 'recursive call cycle'
    _check_cli_rejection(tmp_path, profile, source, marker, message)


def _check_cli_rejection(tmp_path, profile, source, marker, message):
    """Exercise the real CLI exit path, without pytest's exception suppression."""
    path = tmp_path / 'selectors.gelb'
    path.write_text(source)
    command = [sys.executable, '-m', 'gelb.gelbc', str(path)]
    if profile == 'diagnostics':
        command += ['--diagnostics-json']
    elif profile == 'analysis':
        command = [sys.executable, '-m', 'gelb.visualization.gelb_view', 'source',
                   str(path), '--export-json', str(tmp_path / 'source.json')]
    else:
        command += ['-b', 'cpu_fortran_serial', '-o', str(tmp_path / 'source.f90')]
    env = dict(os.environ, PYTHONUNBUFFERED='1', QT_QPA_PLATFORM='offscreen')
    env.pop('PYTEST_CURRENT_TEST', None)
    result = subprocess.run(command, cwd=Path(__file__).resolve().parents[3], env=env,
                            capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert 'Traceback' not in output and 'RecursionError' not in output, output
    line = next(i for i, text in enumerate(source.splitlines(), 1) if marker in text)
    if profile == 'diagnostics':
        errors = [d for d in json.loads(result.stdout)['diagnostics'] if d['severity'] == 'error']
        assert len(errors) == 1
        assert message in errors[0]['message']
        assert errors[0]['range']['startLine'] == line - 1
        assert errors[0]['range']['startCol'] >= 0
    else:
        assert message in output and f'{line}->' in output, output


@pytest.mark.parametrize('mode', [False, True])
@pytest.mark.parametrize('fail', [False, True])
def test_speculative_evaluation_restores_diagnostic_mode(monkeypatch, mode, fail):
    from gelb.midware.ast_eval import nonfatal_evaluation
    from gelb.utils import config

    monkeypatch.setattr(config, 'DIAGNOSTICS_MODE', mode)
    try:
        with nonfatal_evaluation():
            with nonfatal_evaluation():
                assert config.DIAGNOSTICS_MODE is True
            assert config.DIAGNOSTICS_MODE is True
            if fail:
                raise ValueError('cannot evaluate')
    except ValueError:
        assert fail
    assert config.DIAGNOSTICS_MODE is mode
