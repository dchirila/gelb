#!/usr/bin/env python3
"""
Unit tests for array/scalar binary operation validation.

Tests strict validation rules that prevent mathematically ambiguous operations.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBExTypeError
from gelb.frontend.stage1_frontend import promote_types, validate_types
from gelb.utils import config


def get_fully_validated_ast(gelb_code):
    """Get AST with full frontend pipeline including type validation."""
    config.GELB_SRC_RAW = gelb_code
    ast = get_typed_ast(gelb_code)  # Up to type inference
    ast = promote_types(ast)        # Apply type promotion
    validate_types(ast)             # Apply type validation
    return ast


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

gauge Out(out = {int val;}) {
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

gauge Out(out = {int val;}) {
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
    
    def test_scalar_array_division_rejected(self):
        """Test that scalar / array operations are rejected."""
        test_code = """
simulation_description("Test scalar array division");

lattices {
    lattice f(1, 3, int, 32, false);
}

initializer Init {
    f.out[x | :] = 1 / f.in[x | :];    // scalar / array (ambiguous)
}

dynamic Dyn {
    f.out[x | 0] = 1;
}

gauge Out(out = {int val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        error = exc_info.value
        assert "Cannot perform scalar division by array" in str(error.error)
        assert "mathematically ambiguous" in str(error.error)
        assert "array division scalar" in str(error.hint)
    
    def test_scalar_array_subtraction_rejected(self):
        """Test that scalar - array operations are rejected."""
        test_code = """
simulation_description("Test scalar array subtraction");

lattices {
    lattice f(1, 3, int, 32, false);
}

initializer Init {
    f.out[x | :] = 5 - f.in[x | :];    // scalar - array (ambiguous)
}

dynamic Dyn {
    f.out[x | 0] = 1;
}

gauge Out(out = {int val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        error = exc_info.value
        assert "Cannot perform scalar subtraction by array" in str(error.error)
        assert "mathematically ambiguous" in str(error.error)
    
    def test_scalar_array_exponentiation_rejected(self):
        """Test that scalar ^ array operations are rejected."""
        test_code = """
simulation_description("Test scalar array exponentiation");

lattices {
    lattice f(1, 3, real, 32, false);
}

initializer Init {
    f.out[x | :] = 2.0 ^ f.in[x | :];  // scalar ^ array (ambiguous)
}

dynamic Dyn {
    f.out[x | 0] = 1.0;
}

gauge Out(out = {real val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        error = exc_info.value
        assert "Cannot perform scalar exponentiation by array" in str(error.error)
        assert "mathematically ambiguous" in str(error.error)
    
    def test_array_array_operations_rejected(self):
        """Test that array op array operations are rejected."""
        test_code = """
simulation_description("Test array array operations");

lattices {
    lattice f(1, 3, int, 32, false);
    lattice g(1, 3, int, 32, false);
}

initializer Init {
    f.out[x | :] = f.in[x | :] + g.in[x | :];  // array + array (not supported)
}

dynamic Dyn {
    f.out[x | 0] = 1;
}

gauge Out(out = {int val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        error = exc_info.value
        assert "Cannot perform array addition by array" in str(error.error)
        assert "operation not supported" in str(error.error)
    
    def test_array_array_all_operations_rejected(self):
        """Test that all array op array operations are rejected."""
        operations = [
            ("f.in[x | :] + g.in[x | :]", "addition"),
            ("f.in[x | :] - g.in[x | :]", "subtraction"), 
            ("f.in[x | :] * g.in[x | :]", "multiplication"),
            ("f.in[x | :] / g.in[x | :]", "division"),
        ]
        
        for expr, op_name in operations:
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

gauge Out(out = {{int val;}}) {{
    val = f.in[x | 0];
}}

node_classes {{
    node_class BULK(Init, Dyn, Out);
}}

geometry {{
    nodes[:] = BULK;
}}
"""
            
            with pytest.raises(GeLBExTypeError) as exc_info:
                get_fully_validated_ast(test_code)
            
            error = exc_info.value
            assert f"Cannot perform array {op_name} by array" in str(error.error)
    
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

gauge Out(out = {real val;}) {
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

gauge Out(out = {int val;}) {
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
    
    def test_error_message_quality(self):
        """Test that error messages are clear and helpful."""
        test_code = """
simulation_description("Test error message quality");

lattices {
    lattice data(1, 5, real, 64, true);
}

initializer Init {
    data.out[x | :] = 3.14 / data.in[x | :];
}

dynamic Dyn {
    data.out[x | 0] = 1.0;
}

gauge Out(out = {real val;}) {
    val = data.in[x | 0];
}

node_classes {
    node_class BULK(Init, Dyn, Out);
}

geometry {
    nodes[:] = BULK;
}
"""
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(test_code)
        
        error = exc_info.value
        # Check that the error has proper structure
        assert hasattr(error, 'error')
        assert hasattr(error, 'hint')
        assert hasattr(error, 'node')
        
        # Check error message content
        assert "scalar division by array" in str(error.error)
        assert "mathematically ambiguous" in str(error.error)
        
        # Check hint provides alternative
        assert "array division scalar" in str(error.hint)