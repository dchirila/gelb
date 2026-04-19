#!/usr/bin/env python3

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
from gelb.tests.test_utils import get_fully_validated_ast, get_typed_ast


class TestConstantFoldingWithPipeline:
    """Test constant folding integrated with full compilation pipeline."""
    
    def test_global_constants_folding(self):
        """Test folding in global constant definitions."""
        source = """
        simulation_description("Test constant folding");
        
        global_constants {
            const int A = 5 + 3;
            const int B = 10 - 2;
            const int C = 4 * 5;
            const real D = 15.0 / 3.0;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = A;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        # Check that global constants were folded
        const_stmts = folded_ast.global_constants.stmts
        
        # A = 5 + 3 = 8
        assert isinstance(const_stmts[0].value, IntLiteral_N)
        assert const_stmts[0].value.value == 8
        
        # B = 10 - 2 = 8  
        assert isinstance(const_stmts[1].value, IntLiteral_N)
        assert const_stmts[1].value.value == 8
        
        # C = 4 * 5 = 20
        assert isinstance(const_stmts[2].value, IntLiteral_N)
        assert const_stmts[2].value.value == 20
        
        # D = 15.0 / 3.0 = 5.0
        assert isinstance(const_stmts[3].value, RealLiteral_N)
        assert const_stmts[3].value.value == 5.0
    
    def test_nested_expressions_folding(self):
        """Test folding of nested constant expressions."""
        source = """
        simulation_description("Test nested folding");
        
        global_constants {
            const int NESTED = (2 + 3) * (4 - 1);
            const bool COMPARISON = 5 > 3;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 1;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        const_stmts = folded_ast.global_constants.stmts
        
        # NESTED = (2+3) * (4-1) = 5 * 3 = 15
        assert isinstance(const_stmts[0].value, IntLiteral_N)
        assert const_stmts[0].value.value == 15
        
        # COMPARISON = 5 > 3 = true
        assert isinstance(const_stmts[1].value, BoolLiteral_N)
        assert const_stmts[1].value.value == 'true'
    
    def test_zero_result_for_division_detection(self):
        """Test that expressions evaluating to zero are folded (enables division by zero detection)."""
        source = """
        simulation_description("Test zero folding for division detection");
        
        global_constants {
            const int ZERO_RESULT = 5 - 5;
            const int ANOTHER_ZERO = 10 - 5 - 5;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 1;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        const_stmts = folded_ast.global_constants.stmts
        
        # Both should fold to 0, enabling division by zero detection
        assert isinstance(const_stmts[0].value, IntLiteral_N)
        assert const_stmts[0].value.value == 0
        
        assert isinstance(const_stmts[1].value, IntLiteral_N)
        assert const_stmts[1].value.value == 0
    
    def test_mixed_type_folding(self):
        """Test folding with mixed integer and real types."""
        source = """
        simulation_description("Test mixed type folding");
        
        global_constants {
            const real MIXED = 5 + 2.5;
            const real INT_DIV = 10 / 4;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 1;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        const_stmts = folded_ast.global_constants.stmts

        # MIXED = 5 + 2.5 = 7.5  (int promoted to real, then added)
        assert isinstance(const_stmts[0].value, RealLiteral_N)
        assert const_stmts[0].value.value == 7.5

        # INT_DIV = 10 / 4 = 2  (int / int folds to int via Fortran-style
        # truncating division; the surrounding `const real` declaration
        # promotes the value at use-site, not inside the folded literal)
        assert isinstance(const_stmts[1].value, IntLiteral_N)
        assert const_stmts[1].value.value == 2
    
    def test_division_by_zero_not_folded(self):
        """Test that division by zero is preserved for validation to catch."""
        source = """
        simulation_description("Test division by zero preservation");
        
        global_constants {
            const int SAFE = 10 / 2;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 1 / 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 1;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)

        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)

        # Check that safe int/int division is folded to an integer
        # (not a real literal -- see test_int_division_yields_int_literal)
        const_stmt = folded_ast.global_constants.stmts[0]
        assert isinstance(const_stmt.value, IntLiteral_N)
        assert const_stmt.value.value == 5

        # Check that division by zero in initializer is NOT folded (remains as Div_N)
        init_stmt = folded_ast.initializers.elements[0].stmts[0]
        assert isinstance(init_stmt.rhs, Div_N)
        assert isinstance(init_stmt.rhs.left, IntLiteral_N)
        assert isinstance(init_stmt.rhs.right, IntLiteral_N)
        assert init_stmt.rhs.left.value == 1
        assert init_stmt.rhs.right.value == 0

    def test_int_division_yields_int_literal(self):
        """Regression test: ``const int X = N / 2`` must
        fold to an ``IntLiteral_N``, not a ``RealLiteral_N``.

        Before the fix, ``_evaluate_div`` always used Python's true
        division (``/``), producing a Python float and wrapping it as a
        ``RealLiteral_N`` even when both operands were ints.  The
        backend then emitted code like
        ``integer(8), parameter :: g_x = 32.0d0`` -- a type mismatch
        that gfortran silently narrows but warns about.
        """
        source = """
        simulation_description("Test int/int folding");

        global_constants {
            const int N = 64;
            const int HALF = N / 2;
            const int QUARTER = N / 4;
            const int TRUNC = 7 / 2;
            const int NEG = -7 / 2;
        }

        lattices { lattice f(1, 1, int, 16, false); }
        initializer Init { f.out[x | 0] = 0; }
        dynamic Dyn { f.out[x | 0] = f.in[x | 0]; }
        gauge Out -> (int v) { v = f.in[x | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:] = BULK; }
        """
        ast = get_typed_ast(source)
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)

        const_stmts = folded_ast.global_constants.stmts
        half = const_stmts[1].value
        quarter = const_stmts[2].value
        trunc = const_stmts[3].value
        neg = const_stmts[4].value

        for name, lit, expected in [
            ('HALF', half, 32),
            ('QUARTER', quarter, 16),
            ('TRUNC', trunc, 3),
            ('NEG', neg, -3),
        ]:
            assert isinstance(lit, IntLiteral_N), \
                f"{name} should fold to IntLiteral_N, got {type(lit).__name__}"
            assert lit.value == expected, \
                f"{name} should be {expected}, got {lit.value}"


class TestConstantFoldingEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_unary_minus_folding(self):
        """Test folding of unary minus operations."""
        source = """
        simulation_description("Test unary minus folding");
        
        global_constants {
            const int NEG_INT = -42;
            const real NEG_REAL = -3.14;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 1;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        const_stmts = folded_ast.global_constants.stmts
        
        # NEG_INT = -42
        assert isinstance(const_stmts[0].value, IntLiteral_N)
        assert const_stmts[0].value.value == -42
        
        # NEG_REAL = -3.14
        assert isinstance(const_stmts[1].value, RealLiteral_N)
        assert const_stmts[1].value.value == -3.14
    
    def test_logical_operations_folding(self):
        """Test folding of logical operations."""
        source = """
        simulation_description("Test logical folding");
        
        global_constants {
            const bool AND_RESULT = true && false;
            const bool OR_RESULT = false || true;
            const bool NOT_RESULT = !true;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 1;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        const_stmts = folded_ast.global_constants.stmts
        
        # AND_RESULT = true && false = false
        assert isinstance(const_stmts[0].value, BoolLiteral_N)
        assert const_stmts[0].value.value == 'false'
        
        # OR_RESULT = false || true = true
        assert isinstance(const_stmts[1].value, BoolLiteral_N)
        assert const_stmts[1].value.value == 'true'
        
        # NOT_RESULT = !true = false
        assert isinstance(const_stmts[2].value, BoolLiteral_N)
        assert const_stmts[2].value.value == 'false'


class TestConstantFoldingGeometryPaints:
    """Test folding inside geometry paint statements.

    Regression guard: the geometry block's local symbol table is empty
    (geometry holds no locally-declared symbols), so ``visitIdentifier_N``
    must NOT early-out on a falsy ``symbol_table`` -- it must follow the
    hierarchical lookup into the parent table to resolve global constants
    like NY. Previously, ``if symbol_table:`` short-circuited because
    SymbolsTable.__len__ counts only LOCAL symbols, leaving NY-1
    unfolded and causing StencilExtractionVisitor to record the paint
    as a full-grid range.
    """

    SOURCE = """
    simulation_description("Geometry paint folding");

    global_constants {
        const int NX = 8;
        const int NY = 8;
    }

    lattices { lattice f(2, 9, real, {NX, NY}, {true, false}); }

    initializer InitF { f.out[x, y | :] = {0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0}; }
    dynamic DynF { f.out[x, y | :] = f.in[x, y | :]; }
    gauge GaugeF -> (real v) { v = f.in[x, y | 0]; }

    node_classes {
        node_class FLUID(InitF, DynF, GaugeF);
        node_class WALL_BOT(InitF, DynF, GaugeF);
        node_class WALL_TOP(InitF, DynF, GaugeF);
    }

    geometry {
        nodes[:, :] = FLUID;
        nodes[:, 0] = WALL_BOT;
        nodes[:, NY - 1] = WALL_TOP;
    }
    """

    def test_identifier_in_geometry_paint_is_folded(self):
        """``NY`` inside a paint statement must be folded to an IntLiteral."""
        ast = get_typed_ast(self.SOURCE)
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)

        # The third paint statement is `nodes[:, NY - 1] = WALL_TOP`.
        paint = folded_ast.geometry.stmts[2]
        y_range = paint.lhs.elements[1]
        # After folding, NY - 1 = 8 - 1 = 7. Both low and high of this
        # single-element range should therefore be an IntLiteral_N(7).
        assert isinstance(y_range.low, IntLiteral_N), (
            f"expected IntLiteral_N after folding, got "
            f"{type(y_range.low).__name__}"
        )
        assert y_range.low.value == 7
        assert isinstance(y_range.high, IntLiteral_N)
        assert y_range.high.value == 7

    def test_nonzero_boundary_paint_extracts_to_literal_range(self):
        """End-to-end: the paint ``nodes[:, NY-1] = WALL_TOP`` reaches the
        stencil extractor as a concrete (NY-1, NY-1) range, NOT as a
        full-range ``None`` placeholder.

        This guards against the original failure mode: unfolded NY-1
        caused StencilExtractionVisitor._try_eval_int() to return None,
        which made the extractor fall through to ``ranges.append(None)``
        -- silently turning a wall boundary into a full-grid paint and
        breaking out-of-bounds validation for non-local stencils.
        """
        from gelb.midware.stage2_midware import extract_stencils
        ast = get_typed_ast(self.SOURCE)
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        stencils = extract_stencils(folded_ast)

        paints_by_nc = {p.node_class: p for p in stencils.geometry_paints}
        assert "WALL_TOP" in paints_by_nc
        wall_top_paint = paints_by_nc["WALL_TOP"]
        # x range is `:` -> None (full range); y range is NY-1 -> (7, 7)
        assert wall_top_paint.ranges[0] is None
        assert wall_top_paint.ranges[1] == (7, 7), (
            f"expected (7, 7), got {wall_top_paint.ranges[1]!r}"
        )


class TestDeclaredWidths:
    """A folded value takes the width it is declared with (a width once
    lost between a constant's declaration and its use): a real32
    constant, cast or arithmetic result is rounded to binary32 when
    folded, an int32 one wraps, and widening it again gives the rounded
    value.  The expectations are independent: binary32 has 24
    significand bits, so 16777217 rounds to 16777216."""

    _PROGRAM = """
    simulation_description("declared widths");
    global_constants {
        const real32 A = real32(16777217.0);
        const real32 B = 16777217.0;
        const real C = real(B);
        const int32 D = int32(2147483648);
        const real32 E = A + 1.0;
        const real E2 = real(E);
        const array[real32, 2] F = {16777217.0, 0.0};
        const real G = sum(F);
        const real H = real(real32(16777217));
        const real P = 7;
        const real Q = 2;
        const real R = P / Q;
        const real S = 16777217 - real32(16777216);
        const array[real32, 2] ARR = {16777217, -16777216};
        const real U = sum(ARR);
        const array[real, 2] V = {1, 2};
        const real W = sum(V);
        const array[real32, 2] ARR2 = {16777217.0, 0.0};
        const array[real, 2] WIDE = ARR2 + {0.0, 0.0};
        const real X = sum(WIDE);
        const int VALUE = (int8(7) / int16(2)) * int16(2);
        const int NEG = (int8(-7) / int16(2)) * int16(2);
        const int Q7 = int32(7) / 2;
        const real Y = int32(7) / 2.0;
        const array[real32, 2] DERIVED = {16777216.0, 0.0} + {1.0, 0.0};
        const array[real, 2] WIDE2 = DERIVED + {0.0, 0.0};
        const real X2 = sum(WIDE2);
        const array[real, 2] BIG = {16777216.0, 0.0} + {1.0, 0.0};
        const array[real32, 2] ALIAS = BIG;
        const array[real, 2] WIDE3 = ALIAS + {0.0, 0.0};
        const real X3 = sum(WIDE3);
    }
    lattices { lattice f(1, 1, real, 4, false); }
    initializer I { f.out[x | 0] = 0.0; }
    dynamic Dy { f.out[x | 0] = f.in[x | 0]; }
    gauge Ga -> (real v) { v = f.in[x | 0]; }
    node_classes { node_class BULK(I, Dy, Ga); }
    geometry { nodes[:] = BULK; }
    """

    def _folded(self):
        # through the promotion pass: the real pipeline's wrappers are
        # what the folder must honour.  A definition keeps its
        # value behind the conversion to its declared type; the folded
        # literal is inside.
        ast = get_fully_validated_ast(self._PROGRAM)
        folded = ConstantFoldingVisitor().visit(ast, ast)
        return {stmt.name.name: self._literal(stmt.value)
                for stmt in folded.global_constants.stmts}

    @staticmethod
    def _literal(node):
        while isinstance(node, TypePromotionNode_N):
            node = node.expr
        return node

    def test_a_cast_to_a_narrow_width_folds_to_the_rounded_value(self):
        c = self._folded()
        assert isinstance(c['A'], RealLiteral_N) and c['A'].value == 16777216.0
        assert c['A'].inferred_type.element_dtype == 'real32'
        assert isinstance(c['D'], IntLiteral_N) and c['D'].value == -2147483648

    def test_a_narrow_constant_is_propagated_at_its_width(self):
        c = self._folded()
        # B itself keeps the initializer's payload behind its narrowing
        # wrapper; every use of B sees the real32 value.
        assert isinstance(c['C'], RealLiteral_N) and c['C'].value == 16777216.0
        assert isinstance(c['H'], RealLiteral_N) and c['H'].value == 16777216.0

    def test_arithmetic_on_a_narrow_result_is_rounded(self):
        c = self._folded()
        # 16777216 + 1 is exact in double; storing it in E rounds it
        # away, which every use of E sees (E's own definition keeps the
        # sum behind its narrowing wrapper, like B).
        assert isinstance(c['E2'], RealLiteral_N) and c['E2'].value == 16777216.0

    def test_inlined_array_elements_take_the_element_width(self):
        c = self._folded()
        assert isinstance(c['G'], RealLiteral_N) and c['G'].value == 16777216.0
        # integer elements of a real32 array are real32 values: their
        # sum is exactly 0, not 1
        assert isinstance(c['U'], RealLiteral_N) and c['U'].value == 0.0
        # a real array written with integers sums as reals
        assert isinstance(c['W'], RealLiteral_N) and c['W'].value == 3.0

    def test_a_real_constant_written_as_an_integer_is_a_real(self):
        # P and Q are reals, so P / Q is 3.5: propagating them as integer
        # literals used to fold an integer division (3)
        c = self._folded()
        assert isinstance(c['R'], RealLiteral_N) and c['R'].value == 3.5

    def test_a_promotion_is_applied_before_the_operation_that_reads_it(self):
        # 16777217 promoted to real32 is 16777216, so the difference is 0
        c = self._folded()
        assert isinstance(c['S'], RealLiteral_N) and c['S'].value == 0.0

    def test_an_array_constant_keeps_its_element_width_through_arithmetic(self):
        # ARR2's first element is binary32 16777216; widening it and
        # adding zero keeps that value
        c = self._folded()
        assert isinstance(c['X'], RealLiteral_N) and c['X'].value == 16777216.0

    def test_an_array_initialized_by_an_expression_or_an_alias_is_stored_at_its_width(self):
        # 16777216 + 1 is 16777217 in double; storing it in a real32 array
        # rounds it back, whether the array is computed or aliases a
        # wider one
        c = self._folded()
        assert isinstance(c['X2'], RealLiteral_N) and c['X2'].value == 16777216.0
        assert isinstance(c['X3'], RealLiteral_N) and c['X3'].value == 16777216.0

    def test_integer_division_survives_an_integer_width_promotion(self):
        # int8 / int16 is an integer division after the promotion:
        # (7 / 2) * 2 is 6, (-7 / 2) * 2 is -6 (truncation toward zero)
        c = self._folded()
        assert isinstance(c['VALUE'], IntLiteral_N) and c['VALUE'].value == 6
        assert isinstance(c['NEG'], IntLiteral_N) and c['NEG'].value == -6
        assert isinstance(c['Q7'], IntLiteral_N) and c['Q7'].value == 3
        # and a promotion to a real makes it a real division
        assert isinstance(c['Y'], RealLiteral_N) and c['Y'].value == 3.5
