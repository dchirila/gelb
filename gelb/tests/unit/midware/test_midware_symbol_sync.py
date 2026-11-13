"""Live lexical tables at the midware boundary (developer pipeline manual)."""

import copy
import os
from pathlib import Path
import subprocess
import sys

import pytest

from gelb.compiler_pipeline import compile_source, PipelineOptions, PipelineProfile as Profile
from gelb.frontend.ASTInvariantValidator import check_stage2
from gelb.frontend.SymbolsTable import SymbolsTable
from gelb.gelb_ast import ASTNodes as A
from gelb.gelb_ast.CanonicalType import canonical_from_ast
from gelb.gelb_ast.SymbolDefinition import SymbolDefinition
from gelb.midware.BlockMutationHelper import declare_temp, replace_decl, remove_decl
from gelb.tests.test_utils import minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBInternalInvariantError


def source(body='real u = f.in[x | 0]; val = u;', functions=''):
    return minimal_gelb_program_1d(gauge_content=body).replace(
        'lattice f(1, 1, int,', 'lattice f(1, 1, real,').replace(
        'gauge Out -> (int val)', 'gauge Out -> (real val)') + functions


def compile_ast(text=None, profile=Profile.CODEGEN, **options):
    return compile_source(text or source(), profile, PipelineOptions(**options)).ast


def decl(name='fresh'):
    return A.VariableDeclarationStmt_N(None, A.ArrayDataType_N(None, 'real', None),
                                       A.Identifier_N(None, name), None)


def blocks(ast):
    for group in (ast.initializers, ast.dynamics, ast.gauges,
                  ast.functions if ast.functions is not None else getattr(ast, '_inlined_functions', ())):
        yield from group or ()


def assert_locals(ast):
    for block in blocks(ast):
        live = [s for s in block.stmts if isinstance(s, A.VariableDeclarationStmt_N)]
        symbols = [s for s in block.symbol_defs if s.tag == 'variable declaration']
        assert {s.name for s in symbols} == {s.name.name for s in live}
        assert len(live) == len(symbols)
        for stmt in live:
            symbol = block.symbol_defs.get_symbol_definition_local(stmt.name.name)
            assert symbol.value is stmt
            assert symbol.canonical_type == canonical_from_ast(stmt.data_type)


@pytest.mark.parametrize('missing_table', [False, True])
def test_helper_updates_live_identity_and_types(missing_table):
    block = compile_ast().gauges[0]
    if missing_table:
        block.symbol_defs = None
    first = decl()
    symbol = declare_temp(block, first)
    assert first.data_type.canonical_type == canonical_from_ast(first.data_type)
    second = decl()
    assert replace_decl(block, second) is symbol
    if symbol is not None:
        assert symbol.value is second and symbol.code_range is second.code_range
        assert symbol.canonical_type == second.data_type.canonical_type
    remove_decl(block, 'fresh')
    if not missing_table:
        assert not block.symbol_defs.contains_local('fresh')


@pytest.mark.parametrize('operation', ['duplicate', 'replace', 'remove', 'type'])
def test_helper_violations_are_internal_errors(operation):
    block = compile_ast().gauges[0]
    with pytest.raises(GeLBInternalInvariantError):
        if operation == 'duplicate':
            declare_temp(block, decl('u'))
        elif operation == 'replace':
            replace_decl(block, decl())
        elif operation == 'remove':
            remove_decl(block, 'fresh')
        else:
            value = decl()
            value.data_type.shape = A.Identifier_N(None, 'unknown')
            declare_temp(block, value)


def test_all_seven_mutators_keep_live_entries():
    from gelb.midware.LocalConstantLowering import lower_local_constants
    from gelb.midware.DrawSequencing import sequence_draws
    from gelb.midware.inline_functions import inline_functions
    from gelb.midware.stage2_midware import fold_constants
    from gelb.midware.IntrinsicArgHoisting import hoist_intrinsic_args
    from gelb.midware.ScalarBlockCSEVisitor import cse_scalar_blocks
    from gelb.midware.SliceDFExpansionVisitor import expand_slice_dfs

    text = source('''
        const real k = 3.0;
        real u = f.in[x | 0];
        real a = u * u + 1.0;
        real b = u * u + 2.0;
        array[real, 3] w = {u, a, b};
        real d = dot_prod(w, w * w);
        real c = Outer(2.0);
        real noise = random() - random();
        val = a + b + c + d + noise + k;
    ''', '''
        function Outer(real p) -> (real r) { r = Inner(p); }
        function Inner(real p) -> (real r) { const real m = 2.0; r = p * m; }
    ''').replace('lattice f(1, 1, real,', 'lattice f(1, 9, real,').replace(
        'f.out[x | 0] = 0;', 'f.out[x | :] = 0.0;').replace(
        'f.out[x | 0] = f.in[x | 0];', '''
        real f1 = f.in[x | 0]; real f2 = f.in[x | 1];
        array[real, 9] arr = {1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0} * f1;
        arr = arr * (f1 + f2);
        f.out[x | :] = arr * (f1 + f2);
    ''')
    class Captured(Exception):
        pass
    saved = []
    def capture(ast, stage):
        if stage == 'constant_folding':
            saved.append(ast)
            raise Captured
    with pytest.raises(Captured):
        compile_source(text, Profile.CODEGEN, PipelineOptions(capture_ast=capture))
    ast = saved[0]
    lower_local_constants(ast)
    assert_locals(ast)
    assert any(getattr(s, 'lowered_const', False) for b in blocks(ast) for s in b.stmts)
    sequence_draws(ast)
    assert_locals(ast)
    assert any(s.name.startswith('_gelb_draw_') for b in blocks(ast) for s in b.symbol_defs)
    inline_functions(ast)
    assert_locals(ast)
    assert ast.functions is None and len(ast._inlined_functions) == 2
    before = sum(len(b.symbol_defs) for b in blocks(ast))
    fold_constants(ast, after_inlining=True)
    assert_locals(ast)
    assert sum(len(b.symbol_defs) for b in blocks(ast)) < before
    hoist_intrinsic_args(ast)
    assert_locals(ast)
    assert any(s.name.startswith('_gelb_dpa_') for b in blocks(ast) for s in b.symbol_defs)
    cse_scalar_blocks(ast)
    assert_locals(ast)
    assert any(s.name.startswith('_gelb_pre_cse_') for b in blocks(ast) for s in b.symbol_defs)
    expand_slice_dfs(ast)
    assert_locals(ast)
    names = {s.name for s in ast.dynamics[0].symbol_defs}
    assert 'arr' not in names and {f'arr_{i}' for i in range(9)} <= names
    assert any(name.startswith('_gelb_cse_') for name in names)
    check_stage2(ast)


def test_scalar_rewrite_preserves_declaration_metadata():
    from gelb.midware.ScalarBlockCSEVisitor import ScalarBlockCSEVisitor
    block = compile_ast().gauges[0]
    old = block.symbol_defs.get_symbol_definition_local('u').value
    old.lowered_const = True
    old.inline_calls = (('F', None, 0),)
    old.inline_binding = ('local', old.inline_calls[0])
    old.inferred_type = old.data_type
    visitor = ScalarBlockCSEVisitor()
    visitor._block = block
    new = visitor._rewrite_stmt(old, old.initial_value)
    assert new is not old and block.symbol_defs.get_symbol_definition_local('u').value is new
    for attr in ('lowered_const', 'inline_calls', 'inline_binding', 'inferred_type'):
        assert getattr(new, attr) == getattr(old, attr)


@pytest.mark.parametrize('profile', list(Profile))
@pytest.mark.parametrize('collinearity', [False, True])
def test_stage2_all_profiles(profile, collinearity):
    ast = compile_ast(source(functions='function F(real p) -> (real r) { r = p; }'),
                      profile, enable_collinearity_rewrite=collinearity)
    check_stage2(ast)
    assert_locals(ast)


@pytest.mark.parametrize('profile', [Profile.CODEGEN, Profile.PROGRAM_ANALYSIS])
@pytest.mark.parametrize('fault', ['stale', 'missing', 'orphan', 'dangling', 'function',
                                   'function_ref', 'const', 'function_const', 'type', 'parent',
                                   'duplicate', 'root', 'set', 'array_name', 'node_class'])
def test_corruptions_are_rejected(profile, fault):
    ast = compile_ast(source(functions='function F(real p) -> (real r) { r = p; }'), profile)
    gauge = ast.gauges[0]
    fn = next(b for b in blocks(ast) if isinstance(b, A.FunctionBlock_N))
    symbol = gauge.symbol_defs.get_symbol_definition_local('u')
    if fault == 'stale':
        symbol.value = copy.copy(symbol.value)
    elif fault == 'missing':
        gauge.symbol_defs.symbol_defs.remove(symbol)
    elif fault == 'orphan':
        declare_temp(gauge, decl('ghost'))
    elif fault == 'dangling':
        gauge.stmts[-1].rhs = A.Identifier_N(None, 'nowhere')
    elif fault == 'function':
        ast.symbol_defs.symbol_defs.remove(ast.symbol_defs.get_symbol_definition_local('F'))
    elif fault == 'function_ref':
        fn.stmts[-1].rhs = A.Identifier_N(None, 'nowhere')
    elif fault in ('const', 'function_const'):
        block = ast.dynamics[0] if fault == 'const' else fn
        value = A.ConstantDefinitionStmt_N(None, decl().data_type, A.Identifier_N(None, 'k'), A.RealLiteral_N(None, 1.0))
        block.stmts.append(value)
    elif fault == 'type':
        symbol.canonical_type = None
    elif fault == 'parent':
        gauge.symbol_defs.parent_table = SymbolsTable()
    elif fault == 'duplicate':
        gauge.symbol_defs.symbol_defs.append(symbol)
    elif fault == 'root':
        ast.leaked = None
    elif fault == 'set':
        class Unordered(A.RealLiteral_N):
            def get_children(self):
                return set()
        gauge.stmts[-1].rhs = Unordered(None, 1.0)
    elif fault == 'array_name':
        gauge.stmts[-1].rhs = A.RectSelOfArrayElems_N(None, A.Identifier_N(None, 'nowhere'), A.List_N(None))
    else:
        ast.node_classes.stmts[0].initializer = A.Identifier_N(None, 'nowhere')
    with pytest.raises(GeLBInternalInvariantError):
        check_stage2(ast)


def test_deep_expression_uses_explicit_stack():
    ast = compile_ast()
    dtype = decl().data_type
    dtype.canonical_type = canonical_from_ast(dtype)
    expr = A.RealLiteral_N(None, 1.0)
    expr.inferred_type = dtype
    for _ in range(2500):
        expr = A.Add_N(None, expr, A.RealLiteral_N(None, 1.0))
        expr.inferred_type = dtype
    ast.gauges[0].stmts[-1].rhs = expr
    limit = sys.getrecursionlimit()
    check_stage2(ast)
    assert sys.getrecursionlimit() == limit


@pytest.mark.parametrize('prefix,body', [
    ('_gelb_draw_0', 'val = random() - random() + _gelb_draw_0;'),
    ('_gelb_call_1', 'val = 1.0 + R() + _gelb_call_1;'),
    ('_gelb_dpa_0', 'array[real, 3] w = {u,u,u}; val = dot_prod(w, w*w) + _gelb_dpa_0;'),
    ('_gelb_pre_cse_0', 'real a = u*u+1.0; real b = u*u+2.0; val = a+b+_gelb_pre_cse_0;'),
    ('_gelb_cse_0', 'val = _gelb_cse_0;'),
    ('arr_0', 'val = arr_0;'),
])
def test_user_temporary_names_are_preserved(prefix, body):
    text = source(f'real {prefix} = 5.0; real u = f.in[x | 0]; ' + body,
                  'function R() -> (real r) { r = random(); }')
    # Exercise slice temporaries and scalarized-name collisions in a dynamic.
    text = text.replace('lattice f(1, 1, real,', 'lattice f(1, 9, real,').replace(
        'f.out[x | 0] = 0;', 'f.out[x | :] = 0.0;').replace(
        'f.out[x | 0] = f.in[x | 0];', f'''
        real {prefix} = 5.0; real a = f.in[x | 0]; real b = f.in[x | 1];
        array[real, 9] arr = {{1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0}} * (a+b);
        f.out[x | :] = arr * (a+b) + {prefix};
    ''')
    ast = compile_ast(text)
    assert_locals(ast)
    for block in (ast.gauges[0], ast.dynamics[0]):
        assert block.symbol_defs.get_symbol_definition_local(prefix).value.initial_value.value == 5.0
    if prefix == 'arr_0':
        assert ast.dynamics[0].symbol_defs.contains_local('arr')


def test_hoisted_temporaries_preserve_parent_table_array_reads():
    text = source('''
        array[real, 3] w = {1.0, 2.0, 3.0};
        val = dot_prod(w, w * w) + dot_prod(_gelb_dpa_0, w);
    ''') + 'global_constants { const array[real, 3] _gelb_dpa_0 = {5.0, 5.0, 5.0}; }'
    ast = compile_ast(text)
    block = ast.gauges[0]
    names = {stmt.name.name for stmt in block.stmts
             if isinstance(stmt, A.VariableDeclarationStmt_N)}
    assert '_gelb_dpa_0' not in names
    assert '_gelb_dpa_1' in names
    read = block.stmts[-1].rhs.right.arguments[0]
    assert isinstance(read, A.Identifier_N) and read.name == '_gelb_dpa_0'
    global_symbol = ast.symbol_defs.get_symbol_definition_local(read.name)
    assert global_symbol is not None
    assert not block.symbol_defs.contains_local(read.name)
    assert block.symbol_defs.get_symbol_definition(read.name) is global_symbol


def test_scalarized_names_respect_parent_table_constants():
    text = source().replace('lattice f(1, 1, real,', 'lattice f(1, 9, real,').replace(
        'f.out[x | 0] = 0;', 'f.out[x | :] = 0.0;').replace(
        'f.out[x | 0] = f.in[x | 0];', '''
        array[real, 9] arr = f.in[x | :];
        f.out[x | :] = arr + arr_0;
    ''') + 'global_constants { const real arr_0 = 5.0; }'
    ast = compile_ast(text)
    block = ast.dynamics[0]
    names = {stmt.name.name for stmt in block.stmts
             if isinstance(stmt, A.VariableDeclarationStmt_N)}
    assert 'arr' in names
    assert not {f'arr_{i}' for i in range(9)} & names
    global_symbol = ast.symbol_defs.get_symbol_definition_local('arr_0')
    assert global_symbol is not None
    assert not block.symbol_defs.contains_local('arr_0')
    assert block.symbol_defs.get_symbol_definition('arr_0') is global_symbol


@pytest.mark.parametrize('profile', list(Profile))
def test_plain_process_invariants_never_exit(profile):
    code = '''
from gelb.compiler_pipeline import compile_source, PipelineOptions, PipelineProfile
from gelb.frontend import ASTInvariantValidator as validator
from gelb.midware.BlockMutationHelper import declare_temp
from gelb.gelb_ast import ASTNodes as A
from gelb.tests.test_utils import minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBInternalInvariantError
import sys
text = minimal_gelb_program_1d()
profile = PipelineProfile(sys.argv[1])
original = validator.check_stage2
def corrupt(ast):
    ast.gauges[0].symbol_defs.symbol_defs.clear()
    original(ast)
validator.check_stage2 = corrupt
try:
    compile_source(text, profile)
except GeLBInternalInvariantError:
    print('strict caught')
else:
    raise AssertionError('strict invariant ignored')
result = compile_source(text, profile, PipelineOptions(strict_invariants=False))
assert any('(internal)' in warning[0] for warning in result.warnings)
try:
    block = result.ast.gauges[0]
    decl = A.VariableDeclarationStmt_N(None, A.ArrayDataType_N(None, 'real', None), A.Identifier_N(None, 'z'), None)
    declare_temp(block, decl)
    declare_temp(block, decl)
except GeLBInternalInvariantError:
    print('helper caught')
else:
    raise AssertionError('duplicate ignored')
print('completed')
'''
    env = dict(os.environ)
    env.pop('PYTEST_CURRENT_TEST', None)
    run = subprocess.run([sys.executable, '-c', code, profile.value], env=env,
                         cwd=Path(__file__).resolve().parents[4], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert 'strict caught' in run.stdout and 'helper caught' in run.stdout and 'completed' in run.stdout
    assert '(internal)' in run.stderr


def test_cse_temps_avoid_scalar_names_being_generated():
    text = source().replace('lattice f(1, 1, real,', 'lattice f(1, 9, real,').replace(
        'f.out[x | 0] = 0;', 'f.out[x | :] = 0.0;').replace(
        'f.out[x | 0] = f.in[x | 0];', """
        real a = f.in[x | 0]; real b = f.in[x | 1];
        array[real, 9] _gelb_cse = {1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0} * (a+b);
        f.out[x | :] = _gelb_cse;
        """)
    ast = compile_ast(text)
    assert_locals(ast)
    names = {s.name for s in ast.dynamics[0].symbol_defs}
    assert {f'_gelb_cse_{i}' for i in range(10)} <= names


@pytest.mark.parametrize('slot', ['array', 'expression', 'nonvalue', 'implicit'])
def test_canonical_type_corruption_is_rejected(slot):
    ast = compile_ast()
    if slot == 'array':
        ast.gauges[0].outputs[0].data_type.canonical_type = None
    elif slot == 'expression':
        ast.gauges[0].stmts[-1].rhs.canonical_type = None
    elif slot == 'nonvalue':
        ast.simulation_description.canonical_type = canonical_from_ast(decl().data_type)
    else:
        ast.symbol_defs.get_symbol_definition_local('Nx').canonical_type = None
    with pytest.raises(GeLBInternalInvariantError):
        check_stage2(ast)
