"""Identifier bindings survive inlining (developer compilation pipeline)."""

import pytest

from gelb.compiler_pipeline import compile_source, PipelineOptions, PipelineProfile
from gelb.frontend.ASTInvariantValidator import check_stage2
from gelb.gelb_ast import ASTNodes as A
from gelb.midware.inline_functions import _subst_identifier
from gelb.tests.test_utils import minimal_gelb_program_1d


@pytest.mark.parametrize('tag', ['implicit timestep variable', 'implicit dimension constant',
                                'implicit lattice coordinate', 'variable declaration',
                                'output variable declaration', None])
@pytest.mark.parametrize('substitute', [False, True])
def test_identifier_copy_preserves_binding_but_not_syntactic_name_metadata(tag, substitute):
    original = A.Identifier_N(None, 'parameter')
    original.inferred_type = A.ArrayDataType_N(None, 'int', None)
    original.symbol_tag = 'input parameter' if substitute else tag
    replacement = A.Identifier_N(None, 'caller')
    replacement.symbol_tag = tag
    mapping = {'parameter': replacement} if substitute else {}
    result = _subst_identifier(original, mapping)
    assert result.inferred_type is original.inferred_type
    assert result.canonical_type == original.canonical_type
    assert getattr(result, 'symbol_tag', None) == tag
    name = _subst_identifier(A.Identifier_N(None, 'parameter'), mapping)
    assert not hasattr(name, 'inferred_type')
    assert getattr(name, 'symbol_tag', None) is None


def test_inlined_stores_keep_typed_values_and_caller_bindings():
    source = minimal_gelb_program_1d(gauge_content='''
        int w = t; int q; {w, q} = Two(w);
        {val, q} = Two(t); val = val + q + Mut(Nx);
    ''') + '''
    function Two(int a) -> (int b, int c) { b = a; c = a * a; }
    function Mut(int a) -> (int b) { a = a + 1; int local = a; b = local; }
    '''
    captured = []
    def inspect(ast, stage):
        if stage != 'function_inlining':
            return
        captured.append(stage)
        block = ast.gauges[0]
        stores = [s for s in block.stmts if isinstance(s, A.VariableAssignmentStmt_N)]
        post = next(s for s in stores if s.lhs.name == 'w')
        assert isinstance(post.rhs, A.Identifier_N)
        assert post.rhs.inferred_type.element_dtype == 'int'
        assert post.rhs.canonical_type.dtype == 'int'
        assert post.rhs.canonical_type.dims == ()
        for stmt in block.stmts:
            if isinstance(stmt, A.VariableDeclarationStmt_N):
                assert not hasattr(stmt.name, 'inferred_type')
                assert getattr(stmt.name, 'symbol_tag', None) is None
        stack = list(block.stmts)
        while stack:
            node = stack.pop()
            if isinstance(node, A.Identifier_N) and hasattr(node, 'inferred_type'):
                expected = block.symbol_defs.get_symbol_definition(node.name).tag
                assert node.symbol_tag == expected
            stack.extend(c for c in node.get_children() if isinstance(c, A.Node_N))
    ast = compile_source(source, PipelineProfile.CODEGEN,
                         PipelineOptions(capture_ast=inspect)).ast
    assert captured == ['function_inlining']
    check_stage2(ast)
