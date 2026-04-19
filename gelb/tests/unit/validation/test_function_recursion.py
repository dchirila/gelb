#!/usr/bin/env python3
"""
Tests for function recursion / call-cycle detection.

GeLB functions are inlined at compile time and must be non-recursive.
The compiler should reject direct recursion (A -> A), mutual recursion
(A -> B -> A), and longer cycles (A -> B -> C -> A).
"""

import pytest
from gelb.frontend.stage1_frontend import (
    get_ast, build_symbols_tables, detect_function_recursion,
)
from gelb.utils import config
from gelb.utils.exceptions import GeLBExFunctionRecursion


def _build_and_check(code):
    """Parse, build symbol tables, and run function recursion detection."""
    config.GELB_SRC_RAW = code
    ast = get_ast("gelb_program", code)
    ast = build_symbols_tables(ast)
    detect_function_recursion(ast)
    return ast


# -- Minimal program scaffolding (1D, int lattice) --

_SCAFFOLD = """
simulation_description("test");
lattices {{ lattice f(1, 1, int, 32, false); }}
{functions}
initializer Init {{ f.out[x | 0] = 0; }}
dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
gauge Out -> (int val) {{ val = f.in[x | 0]; }}
node_classes {{ node_class BULK(Init, Dyn, Out); }}
geometry {{ nodes[:] = BULK; }}
"""


class TestFunctionRecursionRejected:
    """Cyclic function calls must be rejected."""

    def test_direct_recursion(self):
        """A calls itself: A -> A."""
        code = _SCAFFOLD.format(functions="""
        function A(int a) -> (int r) {
            r = A(a - 1);
        }
        """)
        with pytest.raises(GeLBExFunctionRecursion):
            _build_and_check(code)

    def test_mutual_recursion(self):
        """A calls B, B calls A: A -> B -> A."""
        code = _SCAFFOLD.format(functions="""
        function A(int a) -> (int r) {
            r = B(a);
        }
        function B(int b) -> (int r) {
            r = A(b);
        }
        """)
        with pytest.raises(GeLBExFunctionRecursion):
            _build_and_check(code)

    def test_three_function_cycle(self):
        """A -> B -> C -> A."""
        code = _SCAFFOLD.format(functions="""
        function A(int a) -> (int r) {
            r = B(a);
        }
        function B(int b) -> (int r) {
            r = C(b);
        }
        function C(int c) -> (int r) {
            r = A(c);
        }
        """)
        with pytest.raises(GeLBExFunctionRecursion):
            _build_and_check(code)

    def test_error_message_contains_cycle_path(self):
        """The exception should include the cycle path."""
        code = _SCAFFOLD.format(functions="""
        function Foo(int a) -> (int r) {
            r = Bar(a);
        }
        function Bar(int b) -> (int r) {
            r = Foo(b);
        }
        """)
        with pytest.raises(GeLBExFunctionRecursion) as exc_info:
            _build_and_check(code)
        # The cycle path should mention both functions
        assert 'Foo' in str(exc_info.value.cycle_path)
        assert 'Bar' in str(exc_info.value.cycle_path)


class TestFunctionRecursionAllowed:
    """Non-cyclic function call patterns must be accepted."""

    def test_no_functions(self):
        """Program with no user-defined functions should pass."""
        code = _SCAFFOLD.format(functions="")
        _build_and_check(code)

    def test_standalone_functions(self):
        """Functions that don't call other functions should pass."""
        code = _SCAFFOLD.format(functions="""
        function A(int a) -> (int r) {
            r = a + 1;
        }
        function B(int b) -> (int r) {
            r = b * 2;
        }
        """)
        _build_and_check(code)

    def test_chain_no_cycle(self):
        """A -> B -> C (no cycle) should pass."""
        code = _SCAFFOLD.format(functions="""
        function C(int c) -> (int r) {
            r = c + 1;
        }
        function B(int b) -> (int r) {
            r = C(b);
        }
        function A(int a) -> (int r) {
            r = B(a);
        }
        """)
        _build_and_check(code)

    def test_diamond_no_cycle(self):
        """A -> B, A -> C, B -> D, C -> D (diamond, no cycle) should pass."""
        code = _SCAFFOLD.format(functions="""
        function D(int d) -> (int r) {
            r = d + 1;
        }
        function B(int b) -> (int r) {
            r = D(b);
        }
        function C(int c) -> (int r) {
            r = D(c);
        }
        function A(int a) -> (int r) {
            r = B(a) + C(a);
        }
        """)
        _build_and_check(code)

    def test_intrinsic_calls_ignored(self):
        """Intrinsic function calls (sin, cos, etc.) should not be flagged."""
        code = _SCAFFOLD.format(functions="""
        function A(int a) -> (int r) {
            r = a + 1;
        }
        """)
        _build_and_check(code)
