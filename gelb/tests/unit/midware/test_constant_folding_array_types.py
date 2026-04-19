#!/usr/bin/env python3
"""
Test constant folding compatibility with ArrayDataType_N system.

These tests verify that ConstantFoldingVisitor preserves the universal
ArrayDataType_N type inference after folding constant expressions.
"""

from gelb.gelb_ast.ASTNodes import *
from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
from gelb.tests.test_utils import get_typed_ast


class TestConstantFoldingArrayTypeCompatibility:
    """Test that constant folding preserves ArrayDataType_N types."""
    
    def test_folded_literals_preserve_array_types(self):
        """Folded constant expressions should preserve ArrayDataType_N types."""
        source = """
        simulation_description("Test constant folding array type preservation");
        
        global_constants {
            const int FOLDED_INT = 5 + 3;
            const real FOLDED_REAL = 2.0 * 3.5;
            const bool FOLDED_BOOL = 10 > 5;
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
        
        # Get AST with full type inference
        ast = get_typed_ast(source)
        
        # Apply constant folding
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        const_stmts = folded_ast.global_constants.stmts
        
        # Check that folded literals have ArrayDataType_N
        folded_int = const_stmts[0].value  # 5 + 3 = 8
        folded_real = const_stmts[1].value  # 2.0 * 3.5 = 7.0  
        folded_bool = const_stmts[2].value  # 10 > 5 = true
        
        # Verify folding occurred
        assert isinstance(folded_int, IntLiteral_N)
        assert folded_int.value == 8
        assert isinstance(folded_real, RealLiteral_N)
        assert folded_real.value == 7.0
        assert isinstance(folded_bool, BoolLiteral_N)
        assert folded_bool.value == 'true'
        
        # The key test: folded literals should have ArrayDataType_N inferred_type
        # This is crucial because downstream passes rely on consistent type representation
        assert hasattr(folded_int, 'inferred_type')
        assert isinstance(folded_int.inferred_type, ArrayDataType_N)
        assert folded_int.inferred_type.element_dtype == "int"
        assert len(folded_int.inferred_type.shape.elements) == 0  # 0-dimensional
        
        assert hasattr(folded_real, 'inferred_type')
        assert isinstance(folded_real.inferred_type, ArrayDataType_N)
        assert folded_real.inferred_type.element_dtype == "real"
        assert len(folded_real.inferred_type.shape.elements) == 0  # 0-dimensional
        
        assert hasattr(folded_bool, 'inferred_type')
        assert isinstance(folded_bool.inferred_type, ArrayDataType_N)
        assert folded_bool.inferred_type.element_dtype == "bool"
        assert len(folded_bool.inferred_type.shape.elements) == 0  # 0-dimensional
    
    def test_nested_folding_preserves_array_types(self):
        """Nested constant folding should preserve ArrayDataType_N at all levels."""
        source = """
        simulation_description("Test nested folding array types");
        
        global_constants {
            const int NESTED = (1 + 2) * (3 + 4);
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
        
        const_stmt = folded_ast.global_constants.stmts[0]
        folded_result = const_stmt.value  # (1+2) * (3+4) = 3 * 7 = 21
        
        # Verify complete folding
        assert isinstance(folded_result, IntLiteral_N)
        assert folded_result.value == 21
        
        # Verify ArrayDataType_N preservation
        assert hasattr(folded_result, 'inferred_type')
        assert isinstance(folded_result.inferred_type, ArrayDataType_N)
        assert folded_result.inferred_type.element_dtype == "int"
        assert len(folded_result.inferred_type.shape.elements) == 0
    
    def test_unary_minus_preserves_array_types(self):
        """Unary minus folding should preserve ArrayDataType_N."""
        source = """
        simulation_description("Test unary minus array types");
        
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
        
        neg_int = const_stmts[0].value
        neg_real = const_stmts[1].value
        
        # Verify folding
        assert isinstance(neg_int, IntLiteral_N)
        assert neg_int.value == -42
        assert isinstance(neg_real, RealLiteral_N)
        assert neg_real.value == -3.14
        
        # Verify ArrayDataType_N preservation
        assert hasattr(neg_int, 'inferred_type')
        assert isinstance(neg_int.inferred_type, ArrayDataType_N)
        assert neg_int.inferred_type.element_dtype == "int"
        assert len(neg_int.inferred_type.shape.elements) == 0
        
        assert hasattr(neg_real, 'inferred_type')
        assert isinstance(neg_real.inferred_type, ArrayDataType_N)
        assert neg_real.inferred_type.element_dtype == "real"
        assert len(neg_real.inferred_type.shape.elements) == 0


class TestArrayElementwiseArithmeticFolding:
    """Test element-wise arithmetic folding on Array1DLiteral_N
    constants -- needed for examples like
    ``const array[real, 9] EX_EX = EX * EX;`` (Smagorinsky LES).
    Without these folds, backends that consume the array as a literal
    initialiser (cpu_highway in particular) crashed with
    ``unexpected 1-D array constant initialiser (Mul_N)``."""

    @staticmethod
    def _fold(source):
        ast = get_typed_ast(source)
        return ConstantFoldingVisitor().visit(ast, ast)

    @staticmethod
    def _const_value(folded_ast, name):
        for stmt in folded_ast.global_constants.stmts.elements:
            if hasattr(stmt, 'name') and stmt.name.name == name:
                return stmt.value
        raise AssertionError(f"constant '{name}' not found")

    def _wrap(self, globals_block):
        return f"""
        simulation_description("Test array elementwise folding");
        global_constants {{
{globals_block}
        }}
        lattices {{ lattice f(1, 3, real, 16, true); }}
        initializer Init {{ f.out[x | 0] = 0; }}
        dynamic Step {{ f.out[x | 0] = f.in[x | 0]; }}
        gauge G -> (real rho) {{ rho = f.in[x | 0]; }}
        node_classes {{ node_class BULK(Init, Step, G); }}
        geometry {{ nodes[:] = BULK; }}
        """

    def test_array_times_array_folds_elementwise(self):
        src = self._wrap(
            "            const array[real, 4] A = {1.0, 2.0, 3.0, 4.0};\n"
            "            const array[real, 4] B = {5.0, 6.0, 7.0, 8.0};\n"
            "            const array[real, 4] C = A * B;"
        )
        folded = self._fold(src)
        c = self._const_value(folded, "C")
        assert isinstance(c, Array1DLiteral_N), \
            f"expected fold to Array1DLiteral_N, got {type(c).__name__}"
        values = [e.value for e in c.value.elements]
        assert values == [5.0, 12.0, 21.0, 32.0]

    def test_array_plus_array_folds(self):
        src = self._wrap(
            "            const array[real, 3] A = {1.0, 2.0, 3.0};\n"
            "            const array[real, 3] B = {10.0, 20.0, 30.0};\n"
            "            const array[real, 3] S = A + B;"
        )
        folded = self._fold(src)
        s = self._const_value(folded, "S")
        assert isinstance(s, Array1DLiteral_N)
        assert [e.value for e in s.value.elements] == [11.0, 22.0, 33.0]

    def test_array_minus_array_folds(self):
        src = self._wrap(
            "            const array[real, 3] A = {10.0, 20.0, 30.0};\n"
            "            const array[real, 3] B = {1.0, 2.0, 3.0};\n"
            "            const array[real, 3] D = A - B;"
        )
        folded = self._fold(src)
        d = self._const_value(folded, "D")
        assert isinstance(d, Array1DLiteral_N)
        assert [e.value for e in d.value.elements] == [9.0, 18.0, 27.0]

    def test_scalar_times_array_broadcasts(self):
        src = self._wrap(
            "            const array[real, 4] A = {1.0, 2.0, 3.0, 4.0};\n"
            "            const array[real, 4] B = 2.0 * A;"
        )
        folded = self._fold(src)
        b = self._const_value(folded, "B")
        assert isinstance(b, Array1DLiteral_N)
        assert [e.value for e in b.value.elements] == [2.0, 4.0, 6.0, 8.0]

    def test_array_times_scalar_broadcasts(self):
        src = self._wrap(
            "            const array[real, 4] A = {1.0, 2.0, 3.0, 4.0};\n"
            "            const array[real, 4] B = A * 0.5;"
        )
        folded = self._fold(src)
        b = self._const_value(folded, "B")
        assert isinstance(b, Array1DLiteral_N)
        assert [e.value for e in b.value.elements] == [0.5, 1.0, 1.5, 2.0]

    def test_smagorinsky_pattern_ex_ex(self):
        """The exact pattern from
        ``examples/lbm/2d/lid_driven_cavity_2d_bgk_smagorinsky.gelb``:
        D2Q9 EX*EX -> element-wise square of the velocity-vector."""
        src = self._wrap(
            "            const array[real, 9] EX = "
            "{0.0, 1.0, 0.0, -1.0, 0.0, 1.0, -1.0, -1.0, 1.0};\n"
            "            const array[real, 9] EX_EX = EX * EX;"
        )
        folded = self._fold(src)
        ex_ex = self._const_value(folded, "EX_EX")
        assert isinstance(ex_ex, Array1DLiteral_N)
        assert [e.value for e in ex_ex.value.elements] == \
            [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 1.0, 1.0, 1.0]

    def test_folded_array_preserves_inferred_type(self):
        """Downstream passes (e.g. the cpu_highway backend's array-
        const emitter) require the folded literal to carry an
        ``ArrayDataType_N`` of the right element kind."""
        src = self._wrap(
            "            const array[real, 3] A = {1.0, 2.0, 3.0};\n"
            "            const array[real, 3] B = A * 2.0;"
        )
        folded = self._fold(src)
        b = self._const_value(folded, "B")
        assert hasattr(b, 'inferred_type')
        assert isinstance(b.inferred_type, ArrayDataType_N)
        assert b.inferred_type.element_dtype == "real"

    def test_div_and_pow_intentionally_not_folded(self):
        """Element-wise array division and exponentiation are
        deliberately NOT folded (to avoid integer-vs-real semantic
        traps for div, and because pow over arrays isn't an idiom).
        These should pass through as raw ``Div_N`` / ``Pow_N``
        nodes -- a backend that hits them is responsible for emit."""
        src = self._wrap(
            "            const array[real, 3] A = {2.0, 4.0, 8.0};\n"
            "            const array[real, 3] B = {1.0, 2.0, 4.0};\n"
            "            const array[real, 3] Q = A / B;"
        )
        folded = self._fold(src)
        q = self._const_value(folded, "Q")
        # Should NOT fold to an Array1DLiteral_N -- passes through as Div_N
        assert not isinstance(q, Array1DLiteral_N)


class TestConstantFoldingArrayTypeIntegration:
    """Test integration of constant folding with the array type system."""
    
    def test_folded_constants_work_with_type_promotion(self):
        """Folded constants should work seamlessly with type promotion."""
        source = """
        simulation_description("Test folded constants with promotion");
        
        global_constants {
            const int A = 2 + 3;        // Folded to 5
            const real B = 4.0 * 1.5;   // Folded to 6.0
            const real MIXED = A + B;   // Should use folded values: 5 + 6.0 = 11.0
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
        
        # Check individual folded constants
        a_value = const_stmts[0].value  # 2 + 3 = 5
        b_value = const_stmts[1].value  # 4.0 * 1.5 = 6.0
        
        assert isinstance(a_value, IntLiteral_N)
        assert a_value.value == 5
        assert isinstance(a_value.inferred_type, ArrayDataType_N)
        assert a_value.inferred_type.element_dtype == "int"
        
        assert isinstance(b_value, RealLiteral_N)
        assert b_value.value == 6.0
        assert isinstance(b_value.inferred_type, ArrayDataType_N)
        assert b_value.inferred_type.element_dtype == "real"
        
        # Check that MIXED expression - this demonstrates advanced constant propagation
        mixed_value = const_stmts[2].value
        
        # The constant folding is sophisticated enough to evaluate A + B even though
        # A and B are identifiers, because their values were already folded to literals
        assert isinstance(mixed_value, RealLiteral_N)
        assert mixed_value.value == 11.0  # 5 + 6.0 = 11.0
        assert isinstance(mixed_value.inferred_type, ArrayDataType_N)
        assert mixed_value.inferred_type.element_dtype == "real"