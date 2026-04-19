#!/usr/bin/env python3
"""
Tests for explicit type-cast intrinsics: int(x), real(x), int8(x), ...

These let users opt into lossy downcasts (like real -> int) that the
implicit-promotion system rejects.  Behavior:

- All 9 width variants are exposed: int, int8, int16, int32, int64,
  real, real16, real32, real64.
- Casts work element-wise on arrays (the result preserves shape).
- real -> int truncates toward zero (Fortran's int() semantics).
- bool -> int: true -> 1, false -> 0.
"""

import pytest
from gelb.tests.test_utils import get_typed_ast
from gelb.gelb_ast.ASTNodes import (
    IntrinsicFunctionCall_N, IntLiteral_N, RealLiteral_N, BoolLiteral_N,
)


def _make_program(global_const_body, init_body="f.out[x | 0] = 0;"):
    return f"""
    simulation_description("test");
    global_constants {{
        {global_const_body}
    }}
    lattices {{ lattice f(1, 1, int, 16, false); }}
    initializer Init {{ {init_body} }}
    dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
    gauge Out -> (int v) {{ v = f.in[x | 0]; }}
    node_classes {{ node_class BULK(Init, Dyn, Out); }}
    geometry {{ nodes[:] = BULK; }}
    """


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------

class TestCastParsing:

    def test_int_call_parses_as_intrinsic(self):
        """Verify the parser produces an IntrinsicFunctionCall_N for int()."""
        from gelb.frontend.stage1_frontend import get_ast as raw_get_ast
        code = _make_program("const real PI = 3.14; const int N = int(PI);")
        raw_ast = raw_get_ast("gelb_program", code)
        n_stmt = raw_ast.global_constants.stmts.elements[1]
        # ConstantDefinitionStmt_N has a 'value' field holding the RHS expr
        rhs = n_stmt.value
        assert isinstance(rhs, IntrinsicFunctionCall_N)
        assert rhs.function_name == 'int'

    def test_real_call_parses_as_intrinsic(self):
        from gelb.frontend.stage1_frontend import get_ast as raw_get_ast
        code = _make_program("const int N = 5; const real X = real(N);")
        raw_ast = raw_get_ast("gelb_program", code)
        x_stmt = raw_ast.global_constants.stmts.elements[1]
        assert isinstance(x_stmt.value, IntrinsicFunctionCall_N)
        assert x_stmt.value.function_name == 'real'

    def test_all_cast_variants_parse(self):
        # real16 is not in this version (user manual, Numerical semantics:
        # Not in this version): the
        # parser rejects the cast, see test_type_rules.py.
        for target in ['int', 'int8', 'int16', 'int32', 'int64',
                       'real', 'real32', 'real64']:
            code = _make_program(
                f"const real PI = 3.14; const {target} N = {target}(PI);"
                if target.startswith('int') else
                f"const int X = 5; const {target} Y = {target}(X);"
            )
            # Just check it doesn't error out
            ast = get_typed_ast(code)
            assert ast is not None, f"Failed for {target}"


# ----------------------------------------------------------------------
# Constant folding
# ----------------------------------------------------------------------

class TestCastFolding:

    def _fold(self, source):
        from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
        ast = get_typed_ast(source)
        return ConstantFoldingVisitor().visit(ast, ast)

    def test_int_of_real_truncates_toward_zero(self):
        ast = self._fold(_make_program(
            "const int A = int(3.7);"
            "const int B = int(-3.7);"
            "const int C = int(0.99);"
            "const int D = int(-0.99);"
        ))
        consts = ast.global_constants.stmts.elements
        assert consts[0].value.value == 3
        assert consts[1].value.value == -3
        assert consts[2].value.value == 0
        assert consts[3].value.value == 0
        for c in consts:
            assert isinstance(c.value, IntLiteral_N)

    def test_int_of_int_is_identity(self):
        ast = self._fold(_make_program(
            "const int A = int(42);"
            "const int B = int(-7);"
        ))
        consts = ast.global_constants.stmts.elements
        assert consts[0].value.value == 42
        assert consts[1].value.value == -7
        assert isinstance(consts[0].value, IntLiteral_N)

    def test_real_of_int_promotes(self):
        ast = self._fold(_make_program(
            "const real A = real(5);"
            "const real B = real(-7);"
        ))
        consts = ast.global_constants.stmts.elements
        assert consts[0].value.value == 5.0
        assert consts[1].value.value == -7.0
        assert isinstance(consts[0].value, RealLiteral_N)

    def test_int_of_bool(self):
        ast = self._fold(_make_program(
            "const int A = int(true);"
            "const int B = int(false);"
        ))
        consts = ast.global_constants.stmts.elements
        assert consts[0].value.value == 1
        assert consts[1].value.value == 0
        assert isinstance(consts[0].value, IntLiteral_N)

    def test_real_of_bool(self):
        ast = self._fold(_make_program(
            "const real A = real(true);"
            "const real B = real(false);"
        ))
        consts = ast.global_constants.stmts.elements
        assert consts[0].value.value == 1.0
        assert consts[1].value.value == 0.0
        assert isinstance(consts[0].value, RealLiteral_N)

    def test_explicit_width_int_casts(self):
        ast = self._fold(_make_program(
            "const int8  A = int8(127);"
            "const int16 B = int16(1000);"
            "const int32 C = int32(100000);"
            "const int64 D = int64(1000000000);"
        ))
        consts = ast.global_constants.stmts.elements
        assert consts[0].value.value == 127
        assert consts[1].value.value == 1000
        assert consts[2].value.value == 100000
        assert consts[3].value.value == 1000000000

    def test_explicit_width_real_casts(self):
        ast = self._fold(_make_program(
            "const real32 A = real32(3.14);"
            "const real64 B = real64(2.71);"
        ))
        consts = ast.global_constants.stmts.elements
        assert abs(consts[0].value.value - 3.14) < 1e-6
        assert consts[1].value.value == 2.71


# ----------------------------------------------------------------------
# Backend code generation
# ----------------------------------------------------------------------

class TestCastCodeGen:

    def _generate(self, source):
        from gelb.backends.stage3_backend_cpu_fortran_serial import generate_fortran
        from gelb.midware.inline_functions import inline_functions
        from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
        ast = get_typed_ast(source)
        ast = ConstantFoldingVisitor().visit(ast, ast)
        ast = inline_functions(ast)
        return generate_fortran(ast, num_timesteps=1)

    def test_int_cast_of_runtime_value_emits_int8(self):
        """Casting a non-foldable expression must emit Fortran int(...,8)."""
        # Use a runtime variable so the cast can't be folded away
        source = """
        simulation_description("test");
        lattices { lattice f(1, 1, real, 16, false); }
        initializer Init { f.out[x | 0] = 1.0; }
        dynamic Dyn {
            real r = f.in[x | 0];
            int truncated = int(r);
            f.out[x | 0] = real(truncated);
        }
        gauge Out -> (real v) { v = f.in[x | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:] = BULK; }
        """
        code = self._generate(source)
        # int(real_var) -> int(gelb_b1_g_r, 8)  (default int kind = 8)
        assert 'int(gelb_b1_g_r, 8)' in code
        # real(int_var) -> dble(gelb_b1_g_truncated)
        assert 'dble(gelb_b1_g_truncated)' in code

    def test_explicit_width_casts_emit_correct_kind(self):
        """int8/16/32 casts must emit the right Fortran kind."""
        source = """
        simulation_description("test");
        lattices { lattice f(1, 1, real, 16, false); }
        initializer Init { f.out[x | 0] = 1.0; }
        dynamic Dyn {
            real r = f.in[x | 0];
            int8  a = int8(r);
            int16 b = int16(r);
            int32 c = int32(r);
            f.out[x | 0] = real(a) + real(b) + real(c);
        }
        gauge Out -> (real v) { v = f.in[x | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:] = BULK; }
        """
        code = self._generate(source)
        assert 'int(gelb_b1_g_r, 1)' in code
        assert 'int(gelb_b1_g_r, 2)' in code
        assert 'int(gelb_b1_g_r, 4)' in code
