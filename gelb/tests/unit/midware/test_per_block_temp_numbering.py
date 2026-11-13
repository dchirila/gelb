"""Temporary scopes and emitted code do not depend on declaration order."""

import re

from click.testing import CliRunner
import pytest

from gelb.compiler_pipeline import compile_source, PipelineOptions, PipelineProfile
from gelb.frontend.ASTInvariantValidator import check_stage2
from gelb.gelb_ast import ASTNodes as A
from gelb.gelbc import cli
from gelb.tests.test_utils import minimal_gelb_program_1d, get_ast
from scripts.emission_structural_diff import TEMP_RE


FUNCTIONS = '''
function R() -> (real r) { r = random(); }
function R2() -> (real r) { r = random(); }
function F(real p) -> (real r) { real q = p*p; r = q+1.0; }
'''
CASES = [
    ('_gelb_draw_', 'real result = random() - random();'),
    ('_gelb_call_', 'real result = 1.0 + R();'),
    ('_gelb_dpa_', 'real result = dot_prod(w, w*w);'),
    ('_gelb_pre_cse_', 'real a = u*u+1.0; real b = u*u+2.0; real result = a+b;'),
    ('_gelb_cse_', 'f.out[x | :] = f.in[x | :] * (u+1.0); real result = u;'),
    ('__F_', 'real result = F(u);'),
]


def program(body, second=None, functions=FUNCTIONS, constants=''):
    def statements(text):
        return 'real u = f.in[x | 0]; array[real, 3] w = {u,u,u}; ' + text
    source = minimal_gelb_program_1d(
        global_constants_content=constants,
        geometry_content='nodes[:] = BULK; nodes[2:5] = OTHER;',
        initializer_content=' '.join(f'f.out[x | {i}] = {i}.0;' for i in range(9)),
        dynamic_content=statements(body) + ' f.out[x | 0] = result;',
    ).replace('f(1, 1, int,', 'f(1, 9, real,').replace('(int val)', '(real val)')
    source = source.replace('node_class BULK(Init, Dyn, Out);',
                            'node_class BULK(Init, Dyn, Out); node_class OTHER(Init, Other, Out);')
    return source + functions + '\ndynamic Other { ' + statements(second or body) + ' f.out[x | 0] = result; }\n'


def compile_ast(source, **options):
    ast = compile_source(source, PipelineProfile.CODEGEN, PipelineOptions(**options)).ast
    check_stage2(ast)
    return ast


def names(block):
    return {s.name.name for s in block.stmts if isinstance(s, A.VariableDeclarationStmt_N)}


@pytest.mark.parametrize('prefix,body', CASES)
@pytest.mark.parametrize('collision', ['none', 'local', 'parent'])
def test_restart_and_visible_collisions(prefix, body, collision):
    taken = prefix + '0' + ('_q' if prefix == '__F_' else '')
    constants, second = '', body
    if collision == 'local':
        second = f'real {taken} = 5.0; ' + body
    elif collision == 'parent':
        constants = f'const array[real, 3] {taken} = {{5.0,5.0,5.0}};'
        second += f' result = result + dot_prod({taken}, w);'
    ast = compile_ast(program(body, second, constants=constants))
    for i, block in enumerate(ast.dynamics):
        start = int(collision == 'parent' or (collision == 'local' and i == 1))
        expected = prefix + str(start) + ('_q' if prefix == '__F_' else '')
        assert expected in names(block)
        if prefix == '_gelb_draw_':
            assert prefix + str(start+1) in names(block)
        if collision == 'local' and i == 1:
            assert block.symbol_defs.get_symbol_definition_local(taken).value.initial_value.value == 5.0
        if collision == 'parent':
            assert taken not in names(block)
            assert block.symbol_defs.get_symbol_definition(taken) is ast.symbol_defs.get_symbol_definition_local(taken)
    if collision == 'parent':
        stack, reads = [ast.dynamics[1].stmts], []
        while stack:
            node = stack.pop()
            if isinstance(node, A.Identifier_N) and node.name == taken:
                reads.append(node)
            if isinstance(node, A.Node_N):
                stack.extend(node.get_children())
        assert reads  # The whole global array must survive folding.


def test_calls_of_constants_keep_program_unique_ids():
    seen = []
    def capture(ast, stage):
        if stage == 'function_inlining':
            seen.append((dict(ast.inline_call_args), [names(b) for b in ast.dynamics]))
    ast = compile_ast(program('real live = F(u); real a = F(3.0); real b = F(2.0); real result = live+a+b;'),
                      capture_ast=capture)
    calls, blocks = seen[0]
    assert list(calls) == list(range(6))
    for block_names in blocks:
        assert {f'__F_{i}_q' for i in range(3)} <= block_names
    for block in ast.dynamics:
        values = {s.name.name: s.initial_value for s in block.stmts if isinstance(s, A.VariableDeclarationStmt_N)}
        assert values['a'].value == 10.0 and values['b'].value == 5.0


CHAIN = [
    'function LongAlpha(real p) -> (real value) { value = LongBeta(p); }',
    'function LongBeta(real p) -> (real value) { value = LongGamma(p); }',
    'function LongGamma(real p) -> (real value) { value = LongDelta(p); }',
    'function LongDelta(real p) -> (real value) { real q = p*p; value = q+1.0; }',
]
BACKENDS = [('cpu_fortran_serial', '.f90'), ('cpu_highway', '.cpp'), ('gpu_cuda_cpp', '.cu')]


def emit(tmp_path, source, backend, suffix):
    path, out = tmp_path / 'order.gelb', tmp_path / ('order' + suffix)
    path.write_text(source)
    run = CliRunner().invoke(cli, [str(path), '-b', backend, '-o', str(out), '--nc-output', 'out.nc'])
    assert run.exit_code == 0, run.output
    return out.read_text()


@pytest.mark.parametrize('backend,suffix', BACKENDS)
def test_deep_calls_are_flat_and_function_order_independent(tmp_path, backend, suffix):
    sources = [program('real result = LongAlpha(u);', functions='\n'.join(order))
               for order in (CHAIN, CHAIN[::-1])]
    retained = []
    for source in sources:
        ast = compile_ast(source)
        retained.append([(b.name.name, sorted(names(b))) for b in ast._inlined_functions])
        assert [b.name.name for b in ast._inlined_functions] == ['LongDelta', 'LongGamma', 'LongBeta', 'LongAlpha']
        for block in ast.dynamics:
            temps = {n for n in names(block) if n.startswith('__')}
            assert temps and all(re.fullmatch(r'__Long\w+_\d+_[a-z]+', n) for n in temps)
            assert all(TEMP_RE.fullmatch('g_' + n) for n in temps)
    assert retained[0] == retained[1]
    emissions = [emit(tmp_path, source, backend, suffix) for source in sources]
    assert emissions[0] == emissions[1]
    if suffix == '.f90':
        assert not re.search(r'\bg0_\w+', emissions[0])


@pytest.mark.parametrize('backend,suffix', BACKENDS)
def test_all_block_kinds_reorder_without_emission_changes(tmp_path, backend, suffix):
    body = ' '.join(body.replace('real result =', 'result =') for _, body in CASES)
    body = 'real result = 0.0; ' + body + ' result = result + LongAlpha(u);'
    source = program(body, functions=FUNCTIONS+'\n'.join(CHAIN))
    # Keep geometry and output signatures fixed while permuting declarations.
    def text(node):
        r = node.code_range
        return ''.join(lines[r.start_line-1:r.stop_line])
    # Distinct initializers and gauges exercise their independent counters too.
    source = source.replace('initializer Init {', 'initializer Init { real noise = random()-random();')
    source = source.replace('gauge Out -> (real val) {', 'gauge Out -> (real val) { real noise = random()-random();')
    ast = get_ast('gelb_program', source)
    lines = source.splitlines(True)
    init, gauge = text(ast.initializers[0]), text(ast.gauges[0])
    source += init.replace('Init {', 'InitOther {') + gauge.replace('Out ->', 'OutOther ->')
    source = source.replace('OTHER(Init, Other, Out)', 'OTHER(InitOther, Other, OutOther)')
    # Parsing ranges avoids changing any expression while reversing each group.
    ast = get_ast('gelb_program', source)
    lines = source.splitlines(True)
    reordered = source
    for group in (ast.initializers, ast.dynamics, ast.gauges, ast.functions):
        chunks = [text(node) for node in group]
        for i, chunk in enumerate(chunks):
            reordered = reordered.replace(chunk, f'@@{i}@@', 1)
        for i, chunk in enumerate(reversed(chunks)):
            reordered = reordered.replace(f'@@{i}@@', chunk, 1)
    assert source != reordered
    assert emit(tmp_path, source, backend, suffix) == emit(tmp_path, reordered, backend, suffix)


def test_cse_counter_continues_across_runs_in_each_block():
    body = """
        real a = u*u+1.0; real b = u*u+2.0;
        f.out[x | 1] = a+b;
        real c = u*u*u+1.0; real d = u*u*u+2.0;
        real result = c+d;
    """
    ast = compile_ast(program(body))
    for block in ast.dynamics:
        assert {'_gelb_pre_cse_0', '_gelb_pre_cse_1'} <= names(block)
    for func in ast._inlined_functions:
        if func.name.name in ('R', 'R2'):
            assert '_gelb_draw_0' in names(func)


@pytest.mark.parametrize('b_body,expected', [
    ('r = p;', ['B', 'A', 'Z']),
    ('r = A(p);', ['Z', 'A', 'B']),
])
def test_callee_order_ties_and_synthetic_cycles(b_body, expected):
    from gelb.midware.inline_functions import _callee_order
    functions = [f'function B(real p) -> (real r) {{ {b_body} }}',
                 'function Z(real p) -> (real r) { r = p; }',
                 'function A(real p) -> (real r) { r = B(p); }']
    for order in (functions, functions[::-1]):
        ast = get_ast('gelb_program', program('real result = u;', functions='\n'.join(order)))
        assert [f.name.name for f in _callee_order({f.name.name: f for f in ast.functions})] == expected
