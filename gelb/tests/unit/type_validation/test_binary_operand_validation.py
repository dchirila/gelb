#!/usr/bin/env python3
"""
Unit tests for binary operand validation - array/scalar operation restrictions.

Tests strict validation rules that prevent mathematically ambiguous operations.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d, get_fully_validated_ast
from gelb.utils.exceptions import GeLBExTypeError


class TestBinaryOperandValidation:
    """Test validation of binary operands for array/scalar operations."""
    
    def test_array_scalar_operations_allowed(self):
        """Test that array op scalar operations are allowed."""
        test_code = """
simulation_description("Test");
lattices { lattice f(1, 3, int, 32, false); }
initializer Init {
    f.out[x | :] = f.in[x | :] + 1;    // array + scalar (OK)
    f.out[x | :] = f.in[x | :] / 2;    // array / scalar (OK)
}
dynamic Dyn { f.out[x | 0] = 1; }
gauge Out -> (int val) { val = f.in[x | 0]; }
node_classes { node_class BULK(Init, Dyn, Out); }
geometry { nodes[:] = BULK; }
"""
        
        # Should succeed without exception
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_scalar_array_commutative_allowed(self):
        """Test that scalar op array is allowed for commutative operations."""
        test_code = """
simulation_description("Test");
lattices { lattice f(1, 3, int, 32, false); }
initializer Init {
    f.out[x | :] = 2 + f.in[x | :];    // scalar + array (commutative, OK)
    f.out[x | :] = 3 * f.in[x | :];    // scalar * array (commutative, OK)
}
dynamic Dyn { f.out[x | 0] = 1; }
gauge Out -> (int val) { val = f.in[x | 0]; }
node_classes { node_class BULK(Init, Dyn, Out); }
geometry { nodes[:] = BULK; }
"""
        
        # Should succeed without exception
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_scalar_array_division_allowed(self):
        """Test that scalar / array operations are allowed (element-wise broadcast)."""
        test_code = """
simulation_description("Test");
lattices { lattice f(1, 3, int, 32, false); }
initializer Init {
    f.out[x | :] = 1 / f.in[x | :];    // scalar / array (broadcast)
}
dynamic Dyn { f.out[x | 0] = 1; }
gauge Out -> (int val) { val = f.in[x | 0]; }
node_classes { node_class BULK(Init, Dyn, Out); }
geometry { nodes[:] = BULK; }
"""

        ast = get_fully_validated_ast(test_code)
        assert ast is not None

    def test_scalar_array_subtraction_allowed(self):
        """Test that scalar - array operations are allowed (element-wise broadcast)."""
        test_code = """
simulation_description("Test");
lattices { lattice f(1, 3, int, 32, false); }
initializer Init {
    f.out[x | :] = 5 - f.in[x | :];    // scalar - array (broadcast)
}
dynamic Dyn { f.out[x | 0] = 1; }
gauge Out -> (int val) { val = f.in[x | 0]; }
node_classes { node_class BULK(Init, Dyn, Out); }
geometry { nodes[:] = BULK; }
"""

        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_array_array_elementwise_operations_allowed(self):
        """Test that element-wise array op array with matching shapes is allowed."""
        test_code = """
simulation_description("Test");
lattices {
    lattice f(1, 3, int, 32, false);
    lattice g(1, 3, int, 32, false);
}
initializer Init {
    f.out[x | :] = f.in[x | :] + g.in[x | :];
}
dynamic Dyn { f.out[x | 0] = 1; }
gauge Out -> (int val) { val = f.in[x | 0]; }
node_classes { node_class BULK(Init, Dyn, Out); }
geometry { nodes[:] = BULK; }
"""
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_single_element_selections_are_scalar(self):
        """Test that single element lattice selections work as scalars."""
        test_code = """
simulation_description("Test");
lattices { lattice f(1, 1, int, 32, false); }
initializer Init {
    // f.in[x | 0] is scalar (single element), so scalar / scalar is OK
    f.out[x | 0] = 1 / f.in[x | 0];
}
dynamic Dyn { f.out[x | 0] = 1; }
gauge Out -> (int val) { val = f.in[x | 0]; }
node_classes { node_class BULK(Init, Dyn, Out); }
geometry { nodes[:] = BULK; }
"""
        
        # Should succeed without exception (scalar / scalar)
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    @pytest.mark.parametrize("expr", [
        "f.in[x | :] + g.in[x | :]",
        "f.in[x | :] - g.in[x | :]",
        "f.in[x | :] * g.in[x | :]",
        "f.in[x | :] / g.in[x | :]",
    ])
    def test_all_array_array_elementwise_operations_allowed(self, expr):
        """Test that all element-wise array op array operations are allowed."""
        test_code = f"""
simulation_description("Test");
lattices {{
    lattice f(1, 3, int, 32, false);
    lattice g(1, 3, int, 32, false);
}}
initializer Init {{
    f.out[x | :] = {expr};
}}
dynamic Dyn {{ f.out[x | 0] = 1; }}
gauge Out -> (int val) {{ val = f.in[x | 0]; }}
node_classes {{ node_class BULK(Init, Dyn, Out); }}
geometry {{ nodes[:] = BULK; }}
"""
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_array_array_elementwise_with_real_lattices(self):
        """Test element-wise array ops with real-valued lattices of matching shapes."""
        test_code = """
simulation_description("Test");
lattices {
    lattice data(1, 5, real, 64, true);
    lattice other(1, 5, real, 64, true);
}
initializer Init {
    data.out[x | :] = data.in[x | :] + other.in[x | :];
}
dynamic Dyn { data.out[x | 0] = 1.0; }
gauge Out -> (real val) { val = data.in[x | 0]; }
node_classes { node_class BULK(Init, Dyn, Out); }
geometry { nodes[:] = BULK; }
"""
        ast = get_fully_validated_ast(test_code)
        assert ast is not None