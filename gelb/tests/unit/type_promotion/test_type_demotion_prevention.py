#!/usr/bin/env python3
"""
Unit tests for type demotion prevention in TypePromotionVisitor.

Tests that invalid type promotions (real -> int, int -> bool) are properly rejected.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d, minimal_gelb_program_2d
from gelb.utils.exceptions import GeLBExTypeError
from gelb.frontend.stage1_frontend import promote_types, validate_types
from gelb.utils import config


def get_ast_with_promotion(gelb_code):
    """Get AST up to and including type promotion stage."""
    config.GELB_SRC_RAW = gelb_code
    ast = get_typed_ast(gelb_code)  # This does up to type inference
    ast = promote_types(ast)  # Apply type promotion
    return ast


class TestTypeDemotionPrevention:
    """Test that type demotion is prevented with proper error messages."""
    
    def test_scalar_to_array_real_to_int_rejected(self):
        """Test that assigning real scalar to int array is rejected."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 3] int_array;
                real real_value = 3.14;
                int_array = real_value;
            """
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_ast_with_promotion(test_code)
        
        error = exc_info.value
        assert "Cannot assign 'real' to array of 'int'" in str(error.error)
        assert "would lose precision" in str(error.error)
        assert "bool → int → real" in str(error.hint)
    
    def test_scalar_to_array_int_to_bool_rejected(self):
        """Test that assigning int scalar to bool array is rejected."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[bool, 5] bool_array;
                int int_value = 42;
                bool_array = int_value;
            """
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_ast_with_promotion(test_code)
        
        error = exc_info.value
        assert "Cannot assign 'int' to array of 'bool'" in str(error.error)
        assert "would lose precision" in str(error.error)
    
    def test_scalar_to_array_real_to_bool_rejected(self):
        """Test that assigning real scalar to bool array is rejected."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[bool, 2] bool_array;
                real real_value = 1.5;
                bool_array = real_value;
            """
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_ast_with_promotion(test_code)
        
        error = exc_info.value
        assert "Cannot assign 'real' to array of 'bool'" in str(error.error)
        assert "would lose precision" in str(error.error)
    
    def test_valid_scalar_to_array_promotions(self):
        """Test that valid promotions still work."""
        # bool to int array
        test_code1 = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 3] int_array;
                bool bool_value = true;
                int_array = bool_value;
            """
        )
        ast1 = get_typed_ast(test_code1)
        # Should succeed without exception
        
        # int to real array
        test_code2 = minimal_gelb_program_1d(
            initializer_content="""
                array[real, 4] real_array;
                int int_value = 42;
                real_array = int_value;
            """
        )
        ast2 = get_typed_ast(test_code2)
        # Should succeed without exception
        
        # bool to real array
        test_code3 = minimal_gelb_program_1d(
            initializer_content="""
                array[real, 2] real_array;
                bool bool_value = false;
                real_array = bool_value;
            """
        )
        ast3 = get_typed_ast(test_code3)
        # Should succeed without exception
    
    def test_same_type_scalar_to_array_allowed(self):
        """Test that same-type scalar to array assignment works."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 5] int_array;
                int int_value = 123;
                int_array = int_value;
            """
        )
        ast = get_ast_with_promotion(test_code)
        
        # Find the assignment and verify broadcast node
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[2]  # int_array = int_value
        
        # Should have a broadcast node without promotion
        assert isinstance(assign_stmt.rhs, BroadcastNode_N)
        assert isinstance(assign_stmt.rhs.scalar_expr, Identifier_N)
        assert assign_stmt.rhs.scalar_expr.name == "int_value"
    
    def test_multidimensional_array_type_demotion_rejected(self):
        """Test type demotion prevention for multi-dimensional arrays."""
        test_code = minimal_gelb_program_2d(
            initializer_content="""
                array[int, {3, 4}] int_matrix;
                real real_value = 2.718;
                int_matrix = real_value;
            """
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_ast_with_promotion(test_code)
        
        error = exc_info.value
        assert "Cannot assign 'real' to array of 'int'" in str(error.error)
    
    def test_lattice_output_type_demotion_rejected(self):
        """Test type demotion prevention for lattice output assignments."""
        # minimal_gelb_program_1d doesn't support lattices_content parameter
        # We need to construct the full program manually
        test_code = """
simulation_description("Test lattice type demotion");

lattices {
    lattice f(1, 1, int, 32, false);
}

initializer Init {
    real real_value = 3.14;
    f.out[x | 0] = real_value;
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
        
        # This should be caught by TypeValidationVisitor, not TypePromotionVisitor
        # So we need to run the full pipeline including validation
        with pytest.raises(GeLBExTypeError) as exc_info:
            ast = get_ast_with_promotion(test_code)
            validate_types(ast)  # This is where the error should be caught
        
        error_str = str(exc_info.value)
        assert "real" in error_str and "int" in error_str
    
    def test_error_message_quality(self):
        """Test that error messages are clear and helpful."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 10] counts;
                real temperature = 98.6;
                counts = temperature;  // Line with error
            """
        )
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_ast_with_promotion(test_code)
        
        error = exc_info.value
        # Check that the error has proper structure
        assert hasattr(error, 'error')
        assert hasattr(error, 'hint')
        assert hasattr(error, 'node')
        
        # Check error message content
        assert "real" in str(error.error)
        assert "int" in str(error.error)
        assert "precision" in str(error.error)
        
        # Check hint mentions explicit cast
        assert "cast" in str(error.hint)