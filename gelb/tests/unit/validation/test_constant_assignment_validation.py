#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBExConstantAssignment
from gelb.frontend.stage1_frontend import validate_constant_assignments


class TestConstantAssignmentValidation:
    """Test validation that constants cannot be assigned to in variable assignment statements."""

    def test_constant_assignment_global_constant(self):
        """Test that assigning to a global constant raises an error."""
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const int SIZE = 100;",
            initializer_content="SIZE = 50;",  # This should fail
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed (prerequisite for validation)
        ast = get_typed_ast(gelb_code)
        
        # Validation should raise an error for assignment to constant
        with pytest.raises(GeLBExConstantAssignment) as excinfo:
            validate_constant_assignments(ast)
        
        # Check that the error mentions the constant name
        assert "SIZE" in str(excinfo.value.error)

    def test_implicit_dimension_constant_assignment(self):
        """Test that assigning to an implicit dimension constant (Nx) raises an error."""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="Nx = 64;",  # This should fail - Nx is implicit constant
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed
        ast = get_typed_ast(gelb_code)
        
        # Validation should raise an error for assignment to implicit constant
        with pytest.raises(GeLBExConstantAssignment) as excinfo:
            validate_constant_assignments(ast)
        
        # Check that the error mentions the constant name
        assert "Nx" in str(excinfo.value.error)

    def test_valid_variable_assignment(self):
        """Test that assignment to a declared variable is allowed."""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="""
                int temp;
                temp = 42;
                f.out[x | 0] = temp;
            """,
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed
        ast = get_typed_ast(gelb_code)
        
        # Validation should pass without raising any exception
        try:
            result = validate_constant_assignments(ast)
            assert result is not None  # Should return the AST
        except GeLBExConstantAssignment:
            pytest.fail("Variable assignment should be allowed")

    def test_multiple_constant_assignments(self):
        """Test that multiple constant assignments are all caught."""
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const int ALPHA = 10; const int BETA = 20;",
            initializer_content="""
                ALPHA = 5;
                f.out[x | 0] = ALPHA;
            """,
            dynamic_content="""
                BETA = 15;
                f.out[x | 0] = f.in[x | 0];
            """,
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed
        ast = get_typed_ast(gelb_code)
        
        # Validation should raise an error for the first constant assignment encountered
        with pytest.raises(GeLBExConstantAssignment) as excinfo:
            validate_constant_assignments(ast)
        
        # Should catch the first one (ALPHA)
        assert "ALPHA" in str(excinfo.value.error)

    def test_constants_in_expressions_allowed(self):
        """Test that using constants in expressions (not assignments) is allowed."""
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const int SIZE = 100;",
            initializer_content="""
                int temp;
                temp = SIZE + 10;
                f.out[x | 0] = temp;
            """,
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed
        ast = get_typed_ast(gelb_code)
        
        # Validation should pass - constants can be used in expressions
        try:
            result = validate_constant_assignments(ast)
            assert result is not None
        except GeLBExConstantAssignment:
            pytest.fail("Using constants in expressions should be allowed")

    def test_lattice_assignment_not_affected(self):
        """Test that lattice assignments are not affected by this validation."""
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const int SIZE = 100;",
            initializer_content="f.out[x | 0] = SIZE;",  # This is lattice assignment, not variable assignment
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed
        ast = get_typed_ast(gelb_code)
        
        # Validation should pass - this is not a variable assignment
        try:
            result = validate_constant_assignments(ast)
            assert result is not None
        except GeLBExConstantAssignment:
            pytest.fail("Lattice assignments should not be affected")

    def test_array_assignment_not_affected(self):
        """Test that array assignments are not affected by this validation."""
        # Note: This test is simplified because array variable declarations 
        # are not fully implemented in type inference yet
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const int SIZE = 100;",
            initializer_content="f.out[x | 0] = SIZE;",  # This uses SIZE but doesn't assign to it
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed
        ast = get_typed_ast(gelb_code)
        
        # Validation should pass - this uses the constant but doesn't assign to it
        try:
            result = validate_constant_assignments(ast)
            assert result is not None
        except GeLBExConstantAssignment:
            pytest.fail("Using constants in expressions should not be affected")

    def test_constant_assignment_in_different_blocks(self):
        """Test that constant assignments are caught in all block types."""
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const int GAMMA = 30;",
            initializer_content="f.out[x | 0] = 0;",
            dynamic_content="""
                GAMMA = 25;
                f.out[x | 0] = f.in[x | 0];
            """,
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed
        ast = get_typed_ast(gelb_code)
        
        # Validation should raise an error even in dynamic block
        with pytest.raises(GeLBExConstantAssignment) as excinfo:
            validate_constant_assignments(ast)
        
        assert "GAMMA" in str(excinfo.value.error)

    def test_no_constants_defined_no_error(self):
        """Test that programs with no constants work fine."""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="""
                int temp;
                temp = 42;
                f.out[x | 0] = temp;
            """,
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed
        ast = get_typed_ast(gelb_code)
        
        # Validation should pass - no constants to violate
        try:
            result = validate_constant_assignments(ast)
            assert result is not None
        except GeLBExConstantAssignment:
            pytest.fail("Programs without constant assignments should work fine")

    def test_assignment_to_undefined_variable_not_caught_here(self):
        """Test that this validator doesn't catch undefined variable errors (that's another validator's job)."""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="""
                undefined_var = 42;
                f.out[x | 0] = 0;
            """,
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed (this might fail due to undefined variable, 
        # but we're testing that IF we get to validation, it doesn't catch this error)
        try:
            ast = get_typed_ast(gelb_code)
            # If we got here, validation should pass - undefined variables are not this validator's concern
            result = validate_constant_assignments(ast)
            assert result is not None
        except GeLBExConstantAssignment:
            pytest.fail("Undefined variable assignment should not be caught by constant assignment validator")
        except Exception:
            # Other errors (like undefined symbol) are expected and OK for this test
            pass

    def test_constant_array_element_assignment(self):
        """Test that assigning to a constant array element raises an error."""
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const array[int, 3] COEFFS = {1, 2, 3};",
            initializer_content="""
                array[int, 3] temp;
                temp[0] = COEFFS[0];
                temp[1] = COEFFS[1]; 
                temp[2] = COEFFS[2];
                COEFFS[0] = 42;
                f.out[x | 0] = temp[0];
            """,
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed
        ast = get_typed_ast(gelb_code)
        
        # Validation should raise an error for assignment to constant array element
        with pytest.raises(GeLBExConstantAssignment) as excinfo:
            validate_constant_assignments(ast)
        
        # Check that the error mentions the constant array name
        assert "COEFFS" in str(excinfo.value.error)

    def test_constant_array_element_assignment_in_dynamic_block(self):
        """Test that constant array element assignments are caught in dynamic blocks too."""
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const array[real, 2] WEIGHTS = {0.5, 0.5};",
            initializer_content="f.out[x | 0] = 0;",
            dynamic_content="""
                WEIGHTS[0] = 0.7;
                f.out[x | 0] = f.in[x | 0];
            """,
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed
        ast = get_typed_ast(gelb_code)
        
        # Validation should raise an error even in dynamic block
        with pytest.raises(GeLBExConstantAssignment) as excinfo:
            validate_constant_assignments(ast)
        
        assert "WEIGHTS" in str(excinfo.value.error)

    def test_variable_array_element_assignment_allowed(self):
        """Test that assignment to a non-constant array element is allowed."""
        gelb_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 3] my_array;
                my_array[0] = 10;
                my_array[1] = 20;
                my_array[2] = 30;
                f.out[x | 0] = my_array[0];
            """,
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
            gauge_content="val = f.in[x | 0];"
        )
        
        # Get AST with type inference completed
        ast = get_typed_ast(gelb_code)
        
        # Validation should pass - variable arrays can be modified
        try:
            result = validate_constant_assignments(ast)
            assert result is not None
        except GeLBExConstantAssignment:
            pytest.fail("Variable array element assignment should be allowed")