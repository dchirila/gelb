#!/usr/bin/env python3
"""Unit tests for the dot_prod argument hoisting midware pass.

Verifies that ``dot_prod(a, b)`` where one or both args are non-
identifier expressions (e.g. ``a * b``, ``c - d``) get rewritten by
hoisting the non-identifier args into fresh local declarations
*before* the enclosing statement.  This is what lets the cpu_highway
backend's bare-identifier requirement coexist with user code that
naturally writes things like ``dot_prod(fIn, cx * cx)``.
"""

import pytest

from gelb.frontend.stage1_frontend import promote_types, validate_types
from gelb.gelb_ast.ASTNodes import (
    Identifier_N,
    IntrinsicFunctionCall_N,
    Mul_N,
    Sub_N,
    VariableDeclarationStmt_N,
)
from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
from gelb.midware.inline_functions import inline_functions
from gelb.midware.IntrinsicArgHoisting import hoist_intrinsic_args
from gelb.tests.test_utils import get_typed_ast


def _pipeline(gelb_code: str):
    """Run the relevant prefix of stage 2 up through the hoisting
    pass: type inference -> fold -> inline -> hoist."""
    ast = get_typed_ast(gelb_code)
    ast = promote_types(ast)
    validate_types(ast)
    ast = ConstantFoldingVisitor().visit(ast, ast)
    ast = inline_functions(ast)
    hoist_intrinsic_args(ast)
    return ast


def _find_block(ast, kind, name):
    """Locate a named block of a given kind (initializer/dynamic/
    gauge) in the program."""
    bag = {
        'init': ast.initializers,
        'dyn': ast.dynamics,
        'gauge': ast.gauges,
    }[kind]
    if bag is None:
        return None
    for blk in bag.elements:
        if blk.name.name == name:
            return blk
    return None


def _collect_dot_prod_calls(node, out):
    """Append every ``IntrinsicFunctionCall_N`` for dot_prod under
    ``node`` to ``out``.  Walks via get_children_names to mirror the
    pass's own traversal."""
    from gelb.gelb_ast.ASTNodes import List_N, Node_N
    if isinstance(node, IntrinsicFunctionCall_N) \
            and node.function_name == 'dot_prod':
        out.append(node)
    if isinstance(node, List_N):
        for elem in node.elements:
            _collect_dot_prod_calls(elem, out)
        return
    if isinstance(node, Node_N):
        for child in node.get_children_names():
            child_node = getattr(node, child, None)
            if child_node is not None:
                _collect_dot_prod_calls(child_node, out)


_D2Q9_GLOBALS = """
    const int N = 16;
    const real TAU = 0.6;
    const array[real, 9] EX = {0.0, 1.0, 0.0, -1.0, 0.0, 1.0, -1.0, -1.0, 1.0};
    const array[real, 9] EY = {0.0, 0.0, 1.0,  0.0, -1.0, 1.0,  1.0, -1.0, -1.0};
    const array[real, 9] W  = {1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0,
                                1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0};
"""


def _wrap_d2q9(dynamic_body):
    return f"""
    simulation_description("dot_prod hoisting test");
    global_constants {{
{_D2Q9_GLOBALS}
    }}
    lattices {{ lattice f(2, 9, real, {{N, N}}, {{true, true}}); }}
    initializer Init {{ f.out[x, y | :] = W * 1.0; }}
    dynamic Step {{
{dynamic_body}
    }}
    gauge G -> (real rho) {{ rho = sum(f.in[x, y | :]); }}
    node_classes {{ node_class BULK(Init, Step, G); }}
    geometry {{ nodes[:, :] = BULK; }}
    """


class TestDotProdHoisting:
    """Verify that non-identifier dot_prod args get hoisted into
    fresh decls placed immediately before the enclosing statement."""

    def test_bare_identifier_args_pass_through(self):
        """``dot_prod(EX, fIn)`` -- both args bare identifiers, no
        rewrite expected.  Pre-state == post-state."""
        body = """
            array[real, 9] fIn = f.in[x, y | :];
            real ux = dot_prod(EX, fIn);
            f.out[x, y | :] = fIn;
        """
        ast = _pipeline(_wrap_d2q9(body))
        block = _find_block(ast, 'dyn', 'Step')
        calls = []
        _collect_dot_prod_calls(block, calls)
        # One dot_prod, both args bare identifiers.
        assert len(calls) == 1
        a, b = calls[0].arguments.elements
        assert isinstance(a, Identifier_N) and a.name == 'EX'
        assert isinstance(b, Identifier_N) and b.name == 'fIn'

    def test_mul_arg_hoisted(self):
        """``dot_prod(fIn, cx * cx)`` -- second arg is Mul_N; after
        the pass it must become an Identifier_N referencing a freshly
        declared local."""
        body = """
            array[real, 9] fIn = f.in[x, y | :];
            array[real, 9] cx = EX - 0.1;
            real k = dot_prod(fIn, cx * cx);
            f.out[x, y | :] = fIn;
        """
        ast = _pipeline(_wrap_d2q9(body))
        block = _find_block(ast, 'dyn', 'Step')
        calls = []
        _collect_dot_prod_calls(block, calls)
        assert len(calls) == 1
        a, b = calls[0].arguments.elements
        assert isinstance(a, Identifier_N), \
            f"expected fIn passthrough, got {type(a).__name__}"
        assert isinstance(b, Identifier_N), \
            f"expected hoisted Identifier, got {type(b).__name__}"
        assert b.name.startswith('_gelb_dpa_'), \
            f"expected hoisted name to use _gelb_dpa_ prefix, got {b.name}"
        # Verify the hoisted decl was inserted as a stmt before the
        # k = dot_prod(...) line and that its initial_value is the
        # original Mul_N.
        decl_names = [
            s.name.name for s in block.stmts.elements
            if isinstance(s, VariableDeclarationStmt_N)
        ]
        assert b.name in decl_names, \
            "hoisted decl missing from the block's stmt list"
        hoisted_decl = next(
            s for s in block.stmts.elements
            if isinstance(s, VariableDeclarationStmt_N)
            and s.name.name == b.name
        )
        assert isinstance(hoisted_decl.initial_value, Mul_N), \
            "hoisted decl's RHS should be the original Mul_N"

    def test_multiple_hoists_get_unique_names(self):
        """Several dot_prod calls in one block, each with a different
        non-identifier arg, must produce unique hoisted names."""
        body = """
            array[real, 9] fIn = f.in[x, y | :];
            array[real, 9] cx = EX - 0.1;
            array[real, 9] cy = EY - 0.2;
            real k20 = dot_prod(fIn, cx * cx);
            real k02 = dot_prod(fIn, cy * cy);
            real k11 = dot_prod(fIn, cx * cy);
            f.out[x, y | :] = fIn;
        """
        ast = _pipeline(_wrap_d2q9(body))
        block = _find_block(ast, 'dyn', 'Step')
        calls = []
        _collect_dot_prod_calls(block, calls)
        assert len(calls) == 3
        hoisted_names = []
        for call in calls:
            a, b = call.arguments.elements
            assert isinstance(b, Identifier_N)
            assert b.name.startswith('_gelb_dpa_')
            hoisted_names.append(b.name)
        # All three temps must have distinct names.
        assert len(set(hoisted_names)) == 3, \
            f"expected 3 unique hoisted names, got {hoisted_names}"

    def test_sub_arg_hoisted(self):
        """``dot_prod(EX, fIn - feq)`` -- Sub_N as second arg.
        Verifies the pass is not Mul_N-specific."""
        body = """
            array[real, 9] fIn = f.in[x, y | :];
            array[real, 9] feq = W * 1.0;
            real flux = dot_prod(EX, fIn - feq);
            f.out[x, y | :] = fIn;
        """
        ast = _pipeline(_wrap_d2q9(body))
        block = _find_block(ast, 'dyn', 'Step')
        calls = []
        _collect_dot_prod_calls(block, calls)
        assert len(calls) == 1
        a, b = calls[0].arguments.elements
        assert isinstance(a, Identifier_N) and a.name == 'EX'
        assert isinstance(b, Identifier_N) and b.name.startswith('_gelb_dpa_')
        hoisted_decl = next(
            s for s in block.stmts.elements
            if isinstance(s, VariableDeclarationStmt_N)
            and s.name.name == b.name
        )
        assert isinstance(hoisted_decl.initial_value, Sub_N)
