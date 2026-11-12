"""Computational type metadata and stage-boundary contracts."""
from dataclasses import FrozenInstanceError
import json
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from gelb.compiler_pipeline import compile_source, PipelineOptions, PipelineProfile
from gelb.frontend import ASTInvariantValidator as invariant
from gelb.gelb_ast import ASTNodes as A
from gelb.gelb_ast.CanonicalType import CanonicalType
from gelb.gelb_ast.SymbolDefinition import SymbolDefinition
from gelb.tests.test_utils import get_fully_validated_ast, minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBInternalInvariantError, GeLBExSyntaxError


def items(*values):
    result = A.List_N(None)
    result.elements = list(values)
    return result


def dtype(kind='int', shape=None):
    return A.ArrayDataType_N(None, kind, shape)


def typed(node):
    node.inferred_type = dtype()
    return node


@pytest.mark.parametrize('shape,dims', [(None, ()), (items(), ()), (A.IntLiteral_N(None, 1), (1,)),
    (items(A.IntLiteral_N(None, 2)), (2,)),
    (A.Array1DLiteral_N(None, items(A.IntLiteral_N(None, 2), A.IntLiteral_N(None, 3))), (2, 3))])
@pytest.mark.parametrize('spelling,canonical', [('int64', 'int'), ('real64', 'real')])
def test_shapes_aliases_and_properties(shape, dims, spelling, canonical):
    ast_type = dtype(spelling, shape)
    t = ast_type.canonical_type
    assert ast_type.element_dtype == spelling
    assert t == CanonicalType(canonical, dims)
    assert t.rank == len(dims)
    assert t.is_scalar == (not dims)
    assert t.is_array == bool(dims)
    assert t.size == (6 if dims == (2, 3) else dims[0] if dims else 1)
    with pytest.raises(FrozenInstanceError):
        t.dtype = 'bool'


@pytest.mark.parametrize('kind,dims', [('string', ()), ('int', (0,)), ('real', (-1,)),
                                      ('int', (True,)), ('int', [1])])
def test_invalid_canonical_types(kind, dims):
    with pytest.raises(ValueError):
        CanonicalType(kind, dims)


def test_assignment_sync_and_unresolved_shape():
    node = A.Identifier_N(None, 'a')
    for value in (dtype('real', A.IntLiteral_N(None, 3)), dtype()):
        node.inferred_type = value
        assert node.canonical_type == value.canonical_type
    for value in (None, A.StringType_N(None), dtype('int', A.Identifier_N(None, 'Q'))):
        node.inferred_type = value
        assert node.canonical_type is None


def test_named_extent_is_resolved_before_inference():
    ast = get_fully_validated_ast(minimal_gelb_program_1d(
        global_constants_content='const int Q = 2;',
        gauge_content='array[int, Q] a = {1, 2}; val = a[0];'))
    declaration = ast.gauges[0].stmts[0]
    assert isinstance(declaration.data_type.shape, A.IntLiteral_N)
    assert declaration.data_type.shape.value == 2
    assert declaration.data_type.canonical_type == CanonicalType('int', (2,))
    invariant.check_stage1(ast)


def test_metadata_and_all_child_implementations():
    assert {'inline_call_args', 'scalar_cse_runs', 'scalar_cse_temps', 'canonical_type',
            'has_open_high'} <= A._AST_METADATA_FIELD_NAMES
    r = A.Range_N(None, None, None)
    r.has_open_high = True
    assert r.get_children_names() == ['high', 'low']
    implementations = {c for c in vars(A).values() if isinstance(c, type) and 'get_children' in c.__dict__}
    assert len(implementations) == 9
    nodes = [A.Program_N(None), dtype(), A.StringType_N(None),
             A.TypePromotionNode_N(None, None, dtype()), A.BroadcastNode_N(None, None, dtype()),
             A.IntrinsicFunctionCall_N(None, 'sum', None), A.UserFunctionCall_N(None, None, None),
             A.StringLiteral_N(None, 'text'), A.NodeClassInstaStmt_N(None, None, None, None, None)]
    for node in nodes:
        assert not isinstance(node.get_children(), set)
    result = compile_source(minimal_gelb_program_1d(), PipelineProfile.CODEGEN)
    assert set(result.ast.get_children_names()) == invariant.PROGRAM_FIELDS


def test_deep_expression_uses_explicit_stacks():
    ast = get_fully_validated_ast(minimal_gelb_program_1d())
    chain = typed(A.IntLiteral_N(None, 1))
    for _ in range(2500):
        chain = typed(A.Add_N(None, chain, typed(A.IntLiteral_N(None, 1))))
    ast.gauges[0].stmts[-1].rhs = chain
    invariant.canonicalize_types(ast)
    invariant.check_stage1(ast)


@pytest.mark.parametrize('tag', sorted(invariant.DECLARED | invariant.IMPLICIT | invariant.NONVALUE))
def test_symbol_tags(tag):
    ast = get_fully_validated_ast(minimal_gelb_program_1d())
    symbol = SymbolDefinition('synthetic', tag, SimpleNamespace(data_type=dtype('real')))
    ast.symbol_defs = [symbol]
    invariant.canonicalize_types(ast)
    expected = CanonicalType('real', ()) if tag in invariant.DECLARED else (
        CanonicalType('int', ()) if tag in invariant.IMPLICIT else None)
    assert symbol.canonical_type == expected
    invariant.check_stage1(ast)
    symbol.canonical_type = CanonicalType('bool', ())
    with pytest.raises(GeLBInternalInvariantError):
        invariant.check_stage1(ast)


@pytest.mark.parametrize('damage', ['missing', 'dims', 'dtype', 'shape', 'nonvalue', 'leaked'])
def test_gate_catches_corruption(damage):
    ast = get_fully_validated_ast(minimal_gelb_program_1d())
    node = ast.gauges[0].stmts[-1].rhs
    if damage == 'missing':
        node.canonical_type = None
    elif damage == 'dims':
        node.canonical_type = CanonicalType('int', (2,))
    elif damage == 'dtype':
        node.inferred_type.element_dtype = 'real'
    elif damage == 'shape':
        node.inferred_type.shape = A.IntLiteral_N(None, 2)
    elif damage == 'nonvalue':
        ast.simulation_description.canonical_type = CanonicalType('int', ())
    else:
        ast.leaked = 'metadata'
    with pytest.raises(GeLBInternalInvariantError):
        invariant.check_stage1(ast)


def test_full_singleton_slice_stays_array_and_scalarization_syncs():
    ast = get_fully_validated_ast(minimal_gelb_program_1d(dynamic_content='f.out[x | :] = f.in[x | :];'))
    statement = ast.dynamics[0].stmts[0]
    assert statement.lhs.canonical_type == statement.rhs.canonical_type == CanonicalType('int', (1,))
    from gelb.midware.SliceDFExpansionVisitor import SliceDFExpansionVisitor
    visitor = SliceDFExpansionVisitor({'f': {'q': 1, 'df_type': 'int'}}, {})
    scalar_lhs = visitor._build_single_df_lhs(statement.lhs, 0)
    assert scalar_lhs.canonical_type == CanonicalType('int', ())
    assert statement.lhs.canonical_type.is_array
    # The full singleton range remains an array. Exercise narrowing on a
    # multi-element range, the path used by distribution expansion.
    wider = get_fully_validated_ast(minimal_gelb_program_1d().replace('lattice f(1, 1,', 'lattice f(1, 9,')
        .replace('f.in[x | 0]', 'sum(f.in[x | :])'))
    selection = wider.dynamics[0].stmts[0].rhs.arguments[0]
    scalar = visitor._subst_lattice_in(selection, 0)
    assert scalar.canonical_type == CanonicalType('int', ())
    direct = get_fully_validated_ast(minimal_gelb_program_1d()).dynamics[0].stmts[0]
    assert direct.lhs.canonical_type == direct.rhs.canonical_type == CanonicalType('int', ())


def test_strict_profiles_and_editor_warning_policy(monkeypatch, tmp_path):
    from gelb import gelbc
    def corrupted(_ast):
        raise GeLBInternalInvariantError('deliberate test corruption')
    monkeypatch.setattr(invariant, 'check_stage1', corrupted)
    for profile in PipelineProfile:
        with pytest.raises(GeLBInternalInvariantError):
            compile_source(minimal_gelb_program_1d(), profile)
        result = compile_source(minimal_gelb_program_1d(), profile, PipelineOptions(strict_invariants=False))
        assert any('(internal)' in warning[0] for warning in result.warnings)
    path = tmp_path / 'program.gelb'
    path.write_text(minimal_gelb_program_1d())
    result = CliRunner().invoke(gelbc.cli, [str(path), '--diagnostics-json'])
    assert result.exit_code == 0, result.output
    assert any(d['severity'] == 'warning' and '(internal)' in d['message']
               for d in json.loads(result.output)['diagnostics'])
    path.write_text(minimal_gelb_program_1d(gauge_content='val = missing_name;'))
    result = CliRunner().invoke(gelbc.cli, [str(path), '--diagnostics-json'])
    assert result.exit_code == 1
    assert any(d['severity'] == 'error' for d in json.loads(result.output)['diagnostics'])


@pytest.mark.parametrize('context', ['string', 'multi_output', 'streaming'])
def test_nonvalue_exemptions_are_restricted(context):
    ast = get_fully_validated_ast(minimal_gelb_program_1d())
    if context == 'string':
        ast.gauges[0].stmts[-1].rhs = A.StringLiteral_N(None, 'not a runtime value')
    elif context == 'multi_output':
        call = A.UserFunctionCall_N(None, A.Identifier_N(None, 'F'), items())
        call.function_block = SimpleNamespace(outputs=[None, None])
        ast.gauges[0].stmts[-1] = A.DestructuringAssignmentStmt_N(None, items(), call)
        invariant.check_stage1(ast)
        call.inferred_type = dtype()
    else:
        lattice = A.Identifier_N(None, 'f')
        call = typed(A.IntrinsicFunctionCall_N(None, 'upstream_dfs', items(lattice)))
        ast.gauges[0].stmts[-1].rhs = call
        invariant.check_stage1(ast)
        lattice.inferred_type = dtype()
    with pytest.raises(GeLBInternalInvariantError):
        invariant.check_stage1(ast)


@pytest.mark.parametrize('block', ['initializer', 'dynamic', 'gauge', 'function'])
def test_local_extent_uses_declaration_scope(block):
    content = 'const int Q = 2; const int R = Q + 1; array[int, R] a;'
    kwargs = {block + '_content': content + (' val = 1;' if block == 'gauge' else '')}
    source = minimal_gelb_program_1d(**(kwargs if block != 'function' else {}))
    if block == 'function':
        source += 'function F(int z) -> (int r) { ' + content + ' r = z; }'
    ast = get_fully_validated_ast(source)
    declarations = [node for node, _, _, _ in invariant._walk(ast)
                    if isinstance(node, A.VariableDeclarationStmt_N) and node.name.name == 'a']
    assert len(declarations) == 1
    declared = declarations[0].data_type
    assert isinstance(declared.shape, A.IntLiteral_N)
    assert declared.shape.value == 3
    assert declared.canonical_type == CanonicalType('int', (3,))
    invariant.check_stage1(ast)
    for profile in PipelineProfile:
        assert not compile_source(source, profile).warnings


@pytest.mark.parametrize('extent,dims', [('Nx', (32,)), ('Nx / 2', (16,)),
                                       ('Ny', (32,)), ('{Nx, Ny}', (32, 32))])
def test_grid_extents_are_concrete(extent, dims):
    from gelb.tests.test_utils import minimal_gelb_program_2d
    source = minimal_gelb_program_2d(gauge_content=f'array[int, {extent}] a; val = 1;')
    ast = get_fully_validated_ast(source)
    declared = ast.gauges[0].stmts[0].data_type
    shape = declared.shape
    extents = shape.value.elements if isinstance(shape, A.Array1DLiteral_N) else [shape]
    assert tuple(part.value for part in extents) == dims
    assert all(isinstance(part, A.IntLiteral_N) for part in extents)
    assert declared.canonical_type == CanonicalType('int', dims)
    invariant.check_stage1(ast)
    assert declared.shape is shape
    for profile in PipelineProfile:
        assert not compile_source(source, profile).warnings


def test_shared_function_output_has_concrete_owner_shape():
    source = minimal_gelb_program_1d(global_constants_content='const int Q = 2;',
        gauge_content='const int L = 5; array[int, 2] b = F(3); val = b[0] + L;')
    source += 'function F(int z) -> (array[int, Q] r) { r = {z, z}; }'
    ast = get_fully_validated_ast(source)
    output = ast.functions[0].outputs[0].data_type
    call = next(node for node, _, _, _ in invariant._walk(ast) if isinstance(node, A.UserFunctionCall_N))
    assert call.inferred_type is output
    assert call.canonical_type == output.canonical_type == CanonicalType('int', (2,))
    invariant.check_stage1(ast)
    # Stage-boundary checks must reject an unresolved synthetic extent.
    output.shape = A.Add_N(None, A.Identifier_N(None, 'Q'), A.IntLiteral_N(None, 1))
    with pytest.raises(GeLBInternalInvariantError, match='inconsistent canonical type'):
        invariant.check_stage1(ast)


def test_synthetic_program_without_lattices():
    ast = A.Program_N(None)
    invariant.canonicalize_types(ast)
    invariant.check_stage1(ast)


@pytest.mark.parametrize('owner', ['global', 'function'])
@pytest.mark.parametrize('caller', ['dynamic', 'gauge', 'initializer'])
@pytest.mark.parametrize('shadow', ['int Q = 5', 'real Q = 0.5', 'bool Q = true',
                                  'int Q = 0', 'int Q = -1'])
@pytest.mark.parametrize('expression,kind', [('{value}', 'int'), ('2 * {value}', 'int'),
    ('{value} + {value}', 'int'), ('real({value})', 'real'), ('{value} + 0.5', 'real')])
def test_global_extent_name_cannot_be_shadowed(owner, caller, shadow, expression, kind):
    constants = 'const int Q = 2;'
    if owner == 'global':
        constants += ' const array[int, Q] W = {1, 2};'
    value = 'W' if owner == 'global' else 'F(4)'
    body = f'const {shadow}; array[{kind}, 2] b = {expression.format(value=value)};'
    body += ' val = 1;' if caller == 'gauge' else ' f.out[x | 0] = 1;'
    source = minimal_gelb_program_1d(global_constants_content=constants,
                                   **{caller + '_content': body})
    if owner == 'function':
        source += 'function F(int z) -> (array[int, Q] r) { r = {z, z}; }'
    for profile in PipelineProfile:
        with pytest.raises(GeLBExSyntaxError, match="Q.*global_constants"):
            compile_source(source, profile)


@pytest.mark.parametrize('caller', ['dynamic', 'initializer'])
@pytest.mark.parametrize('shape_kind', ['container', 'partial_slice', 'broadcast'])
def test_shared_shape_containers_and_extent_nodes(caller, shape_kind):
    source = minimal_gelb_program_1d(
        global_constants_content='const int Q = 2; const array[int, {Q, 3}] W = {{1, 2, 3}, {4, 5, 6}};',
        **{caller + '_content': 'const int L = 5; f.out[x | 0] = 1;'})
    ast = get_fully_validated_ast(source)
    declared = ast.global_constants.stmts[1].data_type
    block = (ast.dynamics if caller == 'dynamic' else ast.initializers)[0]
    # Model the sharing used by inferred multidimensional and partial-slice
    # types: a new List_N can retain just one declared extent expression.
    shape = declared.shape
    assert isinstance(shape, A.Array1DLiteral_N)
    if shape_kind == 'partial_slice':
        shape = items(shape.value[0])
    elif shape_kind == 'container':
        shape = shape.value
    shared = dtype('int', shape)
    node = (A.BroadcastNode_N(None, typed(A.IntLiteral_N(None, 1)), shared)
            if shape_kind == 'broadcast' else typed(A.Identifier_N(None, 'synthetic')))
    node.inferred_type = shared
    block.stmts[-1].rhs = node
    invariant.canonicalize_types(ast)
    invariant.check_stage1(ast)
    assert node.canonical_type == CanonicalType('int', (2,) if shape_kind == 'partial_slice' else (2, 3))
    assert declared.canonical_type == CanonicalType('int', (2, 3))
    assert shared.shape is shape
    shared.shape = A.Identifier_N(None, 'Q')
    with pytest.raises(GeLBInternalInvariantError):
        invariant.check_stage1(ast)


def test_concrete_types_do_not_build_extent_bindings(monkeypatch):
    from gelb.frontend.TypeInferenceVisitor import TypeInferenceVisitor
    from gelb.midware import ast_eval

    ast = get_fully_validated_ast(minimal_gelb_program_1d(
        gauge_content='array[int, 2] a = {1, 2}; val = a[0];'))

    def unexpected(*args):
        pytest.fail('concrete types do not need constant evaluation')

    monkeypatch.setattr(ast_eval, 'collect_lattice_info', unexpected)
    monkeypatch.setattr(TypeInferenceVisitor, '_compile_time_bindings', unexpected)
    invariant.canonicalize_types(ast)
    invariant.check_stage1(ast)


def test_inline_copy_shares_type_and_preserves_assignment_sync():
    from gelb.midware.inline_functions import _copy_tree
    original = A.IntLiteral_N(None, 1)
    assert not hasattr(original, 'inferred_type')
    original.inferred_type = dtype('int', A.IntLiteral_N(None, 2))
    copied = _copy_tree(original)
    assert copied.inferred_type is original.inferred_type
    assert vars(copied)['inferred_type'] is original.inferred_type
    copied.inferred_type = dtype('real')
    assert copied.canonical_type == CanonicalType('real', ())
    assert original.canonical_type == CanonicalType('int', (2,))
    assert 'inferred_type' not in copied.get_children_names()


@pytest.mark.parametrize('entry', ['run_analysis_pipeline', 'compile_to_program_analysis'])
def test_program_analysis_entry_points_warn_on_invariants(monkeypatch, tmp_path, entry):
    from gelb import compiler_pipeline
    from gelb.midware import program_analysis
    from gelb.utils.exceptions import GeLBException
    results = []
    compile_file = compiler_pipeline.compile_file

    def capture(*args, **kwargs):
        result = compile_file(*args, **kwargs)
        results.append(result)
        return result

    def corrupted(_ast):
        raise GeLBInternalInvariantError('deliberate analysis corruption')

    monkeypatch.setattr(compiler_pipeline, 'compile_file', capture)
    monkeypatch.setattr(invariant, 'check_stage1', corrupted)
    path = tmp_path / 'analysis.gelb'
    path.write_text(minimal_gelb_program_1d())
    assert getattr(program_analysis, entry)(path) is not None
    assert any('(internal)' in warning[0] for warning in results[0].warnings)
    path.write_text(minimal_gelb_program_1d(gauge_content='val = missing_name;'))
    with pytest.raises(GeLBException):
        getattr(program_analysis, entry)(path)
