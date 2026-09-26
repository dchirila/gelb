#!/usr/bin/env python3
"""
Tests for array-RHS destructuring assignment.

GeLB's destructuring syntax `{a, b, c} = expr;` was originally
restricted to multi-output function calls.  This test file covers the
generalized form where the RHS can be any 1D-array expression
(literal, variable, slice).
"""

import pytest
from gelb.tests.test_utils import get_typed_ast, get_fully_validated_ast
from gelb.utils.exceptions import GeLBExTypeError


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _make_program(init_body):
    """Build a minimal 1D program with a custom initializer body."""
    return f"""
    simulation_description("test");
    lattices {{ lattice f(1, 1, real, 16, false); }}
    initializer Init {{
        {init_body}
        f.out[x | 0] = 0.0;
    }}
    dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
    gauge Out -> (real v) {{ v = f.in[x | 0]; }}
    node_classes {{ node_class BULK(Init, Dyn, Out); }}
    geometry {{ nodes[:] = BULK; }}
    """


def _generate(source):
    from gelb.backends.stage3_backend_cpu_fortran_serial import generate_fortran
    from gelb.midware.inline_functions import inline_functions
    from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
    ast = get_typed_ast(source)
    ast = ConstantFoldingVisitor().visit(ast, ast)
    ast = inline_functions(ast)
    return generate_fortran(ast, num_timesteps=1)


# ----------------------------------------------------------------------
# Frontend validation
# ----------------------------------------------------------------------

class TestArrayDestructuringValidation:

    def test_array_literal_correct_length_accepted(self):
        """`{a, b, c} = {1.0, 2.0, 3.0};` must type-check successfully."""
        code = _make_program("""
            real a;
            real b;
            real c;
            {a, b, c} = {1.0, 2.0, 3.0};
        """)
        # Should not raise
        get_fully_validated_ast(code)

    def test_array_literal_wrong_length_rejected(self):
        """`{a, b} = {1.0, 2.0, 3.0};` must be rejected (length mismatch)."""
        code = _make_program("""
            real a;
            real b;
            {a, b} = {1.0, 2.0, 3.0};
        """)
        with pytest.raises(GeLBExTypeError):
            get_fully_validated_ast(code)

    def test_scalar_rhs_rejected(self):
        """`{a} = 5.0;` must be rejected (cannot destructure a scalar)."""
        code = _make_program("""
            real a;
            {a} = 5.0;
        """)
        with pytest.raises(GeLBExTypeError):
            get_fully_validated_ast(code)

    def test_single_output_function_rejected(self):
        """A single-output function cannot be destructured."""
        code = """
        simulation_description("test");
        lattices { lattice f(1, 1, real, 16, false); }
        function SingleOut(real x) -> (real r) {
            r = x + 1.0;
        }
        initializer Init {
            real a;
            real b;
            {a, b} = SingleOut(3.0);
            f.out[x | 0] = a;
        }
        dynamic Dyn { f.out[x | 0] = f.in[x | 0]; }
        gauge Out -> (real v) { v = f.in[x | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:] = BULK; }
        """
        with pytest.raises(GeLBExTypeError):
            get_fully_validated_ast(code)

    def test_multi_output_function_wrong_arity_rejected(self):
        """A multi-output function with N outputs needs exactly N targets."""
        code = """
        simulation_description("test");
        lattices { lattice f(1, 1, real, 16, false); }
        function ThreeOut(real x) -> (real a, real b, real c) {
            a = x + 1.0;
            b = x + 2.0;
            c = x + 3.0;
        }
        initializer Init {
            real p;
            real q;
            {p, q} = ThreeOut(3.0);
            f.out[x | 0] = p;
        }
        dynamic Dyn { f.out[x | 0] = f.in[x | 0]; }
        gauge Out -> (real v) { v = f.in[x | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:] = BULK; }
        """
        with pytest.raises(GeLBExTypeError):
            get_fully_validated_ast(code)


# ----------------------------------------------------------------------
# Backend codegen
# ----------------------------------------------------------------------

class TestArrayDestructuringCodeGen:

    def test_array_literal_emits_direct_assignments(self):
        """`{a, b} = {1.0, 2.0};` emits two scalar assignments, no temp."""
        code = _make_program("""
            real a;
            real b;
            {a, b} = {1.0, 2.0};
        """)
        fortran = _generate(code)
        assert 'g_a = 1.0' in fortran
        assert 'g_b = 2.0' in fortran
        # No associate block needed for the literal case
        assert 'gelb_destr_tmp' not in fortran

    def test_array_variable_emits_temp(self):
        """`{a, b, c} = arr;` uses an associate temp for safe element access."""
        code = """
        simulation_description("test");
        global_constants {
            const array[real, 3] EX = {1.0, 2.0, 3.0};
        }
        lattices { lattice f(1, 1, real, 16, false); }
        initializer Init {
            real a;
            real b;
            real c;
            {a, b, c} = EX;
            f.out[x | 0] = a;
        }
        dynamic Dyn { f.out[x | 0] = f.in[x | 0]; }
        gauge Out -> (real v) { v = f.in[x | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:] = BULK; }
        """
        fortran = _generate(code)
        assert 'associate (gelb_destr_tmp =>' in fortran
        assert 'end associate' in fortran
        # All three targets should read from the temp
        assert 'g_a = gelb_destr_tmp(' in fortran
        assert 'g_b = gelb_destr_tmp(' in fortran
        assert 'g_c = gelb_destr_tmp(' in fortran

    def test_function_call_destructuring_still_works(self):
        """Regression: the original function-call destructuring path."""
        code = """
        simulation_description("test");
        lattices { lattice f(1, 1, real, 16, false); }
        function TwoOut(real x) -> (real a, real b) {
            a = x + 1.0;
            b = x + 2.0;
        }
        initializer Init {
            real p;
            real q;
            {p, q} = TwoOut(3.0);
            f.out[x | 0] = p;
        }
        dynamic Dyn { f.out[x | 0] = f.in[x | 0]; }
        gauge Out -> (real v) { v = f.in[x | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:] = BULK; }
        """
        fortran = _generate(code)
        # After inlining, function calls become straight-line code,
        # so we just check the program compiles to something that
        # references both targets.
        assert 'g_p' in fortran
        assert 'g_q' in fortran
