#!/usr/bin/env python3
"""
Unit tests for array/scalar binary operation validation.

Tests strict validation rules that prevent mathematically ambiguous operations.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d, get_fully_validated_ast
from gelb.utils.exceptions import GeLBExTypeError


class TestArrayScalarOperationValidation:
    """Test validation of array/scalar binary operations."""
    
    def test_scalar_scalar_operations_allowed(self):
        """Test that scalar op scalar operations are allowed."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                int a = 5;
                int b = 3;
                int result1 = a + b;
                int result2 = a - b;
                int result3 = a * b;
                int result4 = a / b;
            """
        )
        
        # Should succeed without exception
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_array_scalar_operations_allowed(self):
        """Test that array op scalar operations are allowed."""
        test_code = """
simulation_description("Test array scalar operations");

lattices {
    lattice f(1, 3, int, 32, false);
}

initializer Init {
    // All these should be allowed
    f.out[x | :] = f.in[x | :] + 1;    // array + scalar
    f.out[x | :] = f.in[x | :] - 2;    // array - scalar  
    f.out[x | :] = f.in[x | :] * 3;    // array * scalar
    f.out[x | :] = f.in[x | :] / 4;    // array / scalar
}

dynamic Dyn {
    f.out[x | 0] = 1;
}

gauge Out -> (int val) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""
        
        # Should succeed without exception
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_scalar_array_commutative_operations_allowed(self):
        """Test that scalar op array operations are allowed for commutative operations."""
        test_code = """
simulation_description("Test scalar array commutative operations");

lattices {
    lattice f(1, 3, int, 32, false);
}

initializer Init {
    // Commutative operations should be allowed
    f.out[x | :] = 2 + f.in[x | :];    // scalar + array (commutative)
    f.out[x | :] = 3 * f.in[x | :];    // scalar * array (commutative)
}

dynamic Dyn {
    f.out[x | 0] = 1;
}

gauge Out -> (int val) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""
        
        # Should succeed without exception
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_scalar_array_division_allowed(self):
        """Test that scalar / array operations are allowed (element-wise broadcast)."""
        test_code = """
simulation_description("Test scalar array division");

lattices {
    lattice f(1, 3, int, 32, false);
}

initializer Init {
    f.out[x | :] = 1 / f.in[x | :];    // scalar / array (broadcast)
}

dynamic Dyn {
    f.out[x | 0] = 1;
}

gauge Out -> (int val) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""

        ast = get_fully_validated_ast(test_code)
        assert ast is not None

    def test_scalar_array_subtraction_allowed(self):
        """Test that scalar - array operations are allowed (element-wise broadcast)."""
        test_code = """
simulation_description("Test scalar array subtraction");

lattices {
    lattice f(1, 3, int, 32, false);
}

initializer Init {
    f.out[x | :] = 5 - f.in[x | :];    // scalar - array (broadcast)
}

dynamic Dyn {
    f.out[x | 0] = 1;
}

gauge Out -> (int val) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""

        ast = get_fully_validated_ast(test_code)
        assert ast is not None

    def test_scalar_array_exponentiation_allowed(self):
        """Test that scalar ^ array operations are allowed (element-wise broadcast)."""
        test_code = """
simulation_description("Test scalar array exponentiation");

lattices {
    lattice f(1, 3, real, 32, false);
}

initializer Init {
    f.out[x | :] = 2.0 ^ f.in[x | :];  // scalar ^ array (broadcast)
}

dynamic Dyn {
    f.out[x | 0] = 1.0;
}

gauge Out -> (real val) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""

        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_array_array_elementwise_operations_allowed(self):
        """Test that array op array with matching shapes is allowed (element-wise)."""
        test_code = """
simulation_description("Test array array operations");

lattices {
    lattice f(1, 3, int, 32, false);
    lattice g(1, 3, int, 32, false);
}

initializer Init {
    f.out[x | :] = f.in[x | :] + g.in[x | :];
}

dynamic Dyn {
    f.out[x | 0] = 1;
}

gauge Out -> (int val) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""
        # Should not raise -- element-wise array ops with matching shapes are valid
        ast = get_fully_validated_ast(test_code)
        assert ast is not None

    def test_array_array_all_elementwise_operations_allowed(self):
        """Test that all element-wise array op array operations are allowed."""
        operations = [
            "f.in[x | :] + g.in[x | :]",
            "f.in[x | :] - g.in[x | :]",
            "f.in[x | :] * g.in[x | :]",
            "f.in[x | :] / g.in[x | :]",
        ]

        for expr in operations:
            test_code = f"""
simulation_description("Test array array operations");

lattices {{
    lattice f(1, 3, int, 32, false);
    lattice g(1, 3, int, 32, false);
}}

initializer Init {{
    f.out[x | :] = {expr};
}}

dynamic Dyn {{
    f.out[x | 0] = 1;
}}

gauge Out -> (int val) {{
    val = f.in[x | 0];
}}

node_classes {{
    node_class BULK(Init, Dyn, Out);
}}

geometry {{
    nodes[:] = BULK;
}}
"""
            # Should not raise -- element-wise operations with matching shapes
            ast = get_fully_validated_ast(test_code)
            assert ast is not None
    
    def test_mixed_types_with_arrays(self):
        """Test array/scalar operations with type promotion."""
        test_code = """
simulation_description("Test mixed types with arrays");

lattices {
    lattice f(1, 3, real, 32, false);
}

initializer Init {
    // Should work: int scalar + real array
    f.out[x | :] = 1 + f.in[x | :];     // int promoted to real
    
    // Should work: real array * bool scalar  
    f.out[x | :] = f.in[x | :] * true;  // bool promoted to real
}

dynamic Dyn {
    f.out[x | 0] = 1.0;
}

gauge Out -> (real val) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""
        
        # Should succeed without exception
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_single_element_selections_are_scalar(self):
        """Test that single element lattice selections are treated as scalars."""
        test_code = """
simulation_description("Test single element selections are scalar");

lattices {
    lattice f(1, 1, int, 32, false);
}

initializer Init {
    // f.in[x | 0] is a scalar (single element)
    // So 1 / f.in[x | 0] is scalar / scalar (allowed)
    f.out[x | 0] = 1 / f.in[x | 0];
}

dynamic Dyn {
    f.out[x | 0] = 1;
}

gauge Out -> (int val) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""
        
        # Should succeed without exception (scalar / scalar)
        ast = get_fully_validated_ast(test_code)
        assert ast is not None
    
    def test_array_array_elementwise_with_real_lattices(self):
        """Test that element-wise array operations work with real-valued lattices."""
        test_code = """
simulation_description("Test element-wise array operations");

lattices {
    lattice data(1, 5, real, 64, true);
    lattice other(1, 5, real, 64, true);
}

initializer Init {
    data.out[x | :] = data.in[x | :] + other.in[x | :];
}

dynamic Dyn {
    data.out[x | 0] = 1.0;
}

gauge Out -> (real val) {
    val = data.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""
        # Should not raise -- element-wise array operations with matching shapes
        ast = get_fully_validated_ast(test_code)
        assert ast is not None