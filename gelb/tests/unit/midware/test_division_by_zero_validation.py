#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
from gelb.midware.DivisionByZeroValidator import DivisionByZeroValidator
from gelb.utils.exceptions import GeLBExTypeError


class TestDivisionByZeroValidation:
    """Test division by zero detection after constant folding and propagation."""
    
    def test_direct_literal_division_by_zero(self):
        """Test detection of direct literal division by zero."""
        test_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = 1 / 0;"
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)
        assert "cannot divide by zero" in str(exc_info.value.error)
    
    def test_real_literal_division_by_zero(self):
        """Test detection of real literal division by zero."""
        test_code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = 1.5 / 0.0;"
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)
        assert "cannot divide by zero" in str(exc_info.value.error)
    
    def test_constant_propagation_division_by_zero(self):
        """Test detection of division by constant that is zero."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int ZERO = 0;",
            initializer_content="f.out[x | 0] = 1 / ZERO;"
        )
        
        # Get typed AST and fold constants (includes propagation)
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)
    
    def test_expression_folding_division_by_zero(self):
        """Test detection of division by expression that evaluates to zero."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int ZERO = 5 - 5;",
            initializer_content="f.out[x | 0] = 1 / ZERO;"
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)
    
    def test_complex_expression_folding_division_by_zero(self):
        """Test detection with complex expressions that evaluate to zero."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int ZERO = (3 + 2) - (4 + 1);",
            initializer_content="f.out[x | 0] = 1 / ZERO;"
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)
    
    def test_real_constant_expression_division_by_zero(self):
        """Test detection with real constants that evaluate to zero."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const real ZERO = 1.5 - 1.5;",
            initializer_content="f.out[x | 0] = 2.0 / ZERO;"
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)
    
    def test_division_by_zero_in_dynamic_block(self):
        """Test detection in dynamic block."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int ZERO = 0;",
            dynamic_content="f.out[x | 0] = 5 / ZERO;"
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)
    
    def test_division_by_zero_in_global_constants(self):
        """Test detection in global constants block."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="""
                const int ZERO = 1 - 1;
                const int INVALID = 10 / ZERO;
            """
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)
    
    def test_valid_division_passes(self):
        """Test that valid divisions pass validation."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="""
                const int FIVE = 5;
                const int TWO = 2;
                const real RESULT = FIVE / TWO;
            """,
            initializer_content="f.out[x | 0] = 10 / 5;",
            dynamic_content="f.out[x | 0] = 8 / 2;"
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should NOT raise error
        validated_ast = DivisionByZeroValidator().visit(folded_ast, folded_ast)
        assert validated_ast is not None
    
    def test_variable_division_by_constant_zero(self):
        """Test division by variable that's assigned a constant zero."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int ZERO = 0;",
            initializer_content="""
                int divisor;
                divisor = ZERO;
                f.out[x | 0] = 1 / divisor;
            """
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # This should NOT be caught because divisor is a variable, not a constant
        # Division by zero detection only catches compile-time constant zeros
        validated_ast = DivisionByZeroValidator().visit(folded_ast, folded_ast)
        assert validated_ast is not None
    
    def test_nested_division_by_zero(self):
        """Test division by zero in nested expressions."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int ZERO = 0;",
            initializer_content="f.out[x | 0] = 1 + (2 / ZERO);"
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)
    
    def test_multiple_divisions_first_valid_second_invalid(self):
        """Test program with multiple divisions where only one is invalid."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int ZERO = 0;",
            initializer_content="""
                int valid_result = 10 / 2;
                f.out[x | 0] = 1 / ZERO;
            """
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error for the invalid one
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)


class TestDivisionByZeroValidationEdgeCases:
    """Test edge cases for division by zero validation."""
    
    def test_division_by_negative_zero(self):
        """Test detection of division by negative zero."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const real NEG_ZERO = -0.0;",
            initializer_content="f.out[x | 0] = 1.0 / NEG_ZERO;"
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)
    
    def test_division_by_zero_with_type_promotion(self):
        """Test detection when type promotion is involved."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const int ZERO = 0;",
            initializer_content="f.out[x | 0] = 1.5 / ZERO;"  # real / int -> real / real
        )
        
        # Get typed AST and fold constants (after type promotion)
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)
    
    def test_division_by_very_small_number_allowed(self):
        """Test that division by very small (but non-zero) numbers is allowed."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const real SMALL = 0.0001;",
            initializer_content="f.out[x | 0] = 1.0 / SMALL;"
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Should not raise error
        validated_ast = DivisionByZeroValidator().visit(folded_ast, folded_ast)
        assert validated_ast is not None
    
    def test_complex_constant_expression_with_zero_result(self):
        """Test complex expression that evaluates to zero through multiple operations."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="""
                const int A = 5;
                const int B = 3;
                const int C = 2;
                const int ZERO = A - B - C;
            """,
            initializer_content="f.out[x | 0] = 1 / ZERO;"
        )
        
        # Get typed AST and fold constants
        ast = get_typed_ast(test_code)
        folded_ast = ConstantFoldingVisitor().visit(ast, ast)
        
        # Division by zero validation should raise error
        with pytest.raises(GeLBExTypeError) as exc_info:
            DivisionByZeroValidator().visit(folded_ast, folded_ast)
        
        assert "Division by zero" in str(exc_info.value.error)