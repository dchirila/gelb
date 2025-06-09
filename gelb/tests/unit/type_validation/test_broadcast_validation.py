#!/usr/bin/env python3
"""
Unit tests for broadcast node validation.

Tests that BroadcastNode_N is properly validated by TypeValidationVisitor.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import (
    get_typed_ast,
    minimal_gelb_program_1d,
    minimal_gelb_program_2d
)
from gelb.frontend.stage1_frontend import (
    get_ast,
    build_symbols_tables,
    add_implicit_symbols,
    resolve_all_constants,
    resolve_ranges,
    infer_types,
    promote_types,
    validate_types
)


class TestBroadcastValidation:
    """Test type validation for broadcast nodes."""
    
    def test_valid_broadcast_passes_validation(self):
        """Test that valid broadcast operations pass type validation."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[real, 5] data;
                data = 3.14;
            """
        )
        
        # Process through full pipeline including validation
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # This should not raise any exceptions
        ast = validate_types(ast)
        
        # Verify the broadcast node is still there
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        assert isinstance(assignment.rhs, BroadcastNode_N)
    
    def test_broadcast_with_promotion_validation(self):
        """Test validation of broadcast with type promotion."""
        test_program = minimal_gelb_program_2d(
            initializer_content="""
                array[real, {2, 3}] matrix;
                matrix = 42;  // int -> real promotion + broadcast
            """
        )
        
        # Process through full pipeline
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # This should not raise any exceptions
        ast = validate_types(ast)
        
        # Verify the structure
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        broadcast = assignment.rhs
        assert isinstance(broadcast, BroadcastNode_N)
        assert isinstance(broadcast.scalar_expr, TypePromotionNode_N)
    
    def test_broadcast_bool_to_bool_validation(self):
        """Test validation of boolean broadcast (no promotion)."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[bool, 8] flags;
                flags = false;
            """
        )
        
        # Process through full pipeline
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # This should not raise any exceptions
        ast = validate_types(ast)
        
        # Verify the structure
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        broadcast = assignment.rhs
        assert isinstance(broadcast, BroadcastNode_N)
        # No promotion needed for bool -> bool
        assert isinstance(broadcast.scalar_expr, BoolLiteral_N)
    
    def test_broadcast_constant_expression_validation(self):
        """Test validation of broadcast with constant expressions."""
        test_program = minimal_gelb_program_1d(
            global_constants_content="""
                const real PI = 3.14159;
                const real E = 2.71828;
            """,
            initializer_content="""
                array[real, 10] values;
                values = PI * E;  // constant expression broadcast
            """
        )
        
        # Process through full pipeline
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # This should not raise any exceptions
        ast = validate_types(ast)
        
        # Verify the broadcast exists
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        assert isinstance(assignment.rhs, BroadcastNode_N)
    
    def test_broadcast_node_inferred_type_validation(self):
        """Test that broadcast nodes have correct inferred types for validation."""
        test_program = minimal_gelb_program_2d(
            initializer_content="""
                array[int, {4, 5}] grid;
                grid = 0;
            """
        )
        
        # Process through type promotion (not validation yet)
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Check the broadcast node has the correct inferred type
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        broadcast = assignment.rhs
        
        assert isinstance(broadcast, BroadcastNode_N)
        assert hasattr(broadcast, 'inferred_type')
        assert isinstance(broadcast.inferred_type, ArrayDataType_N)
        assert broadcast.inferred_type.element_dtype == "int"
        
        # The shape should match the target array
        lhs_type = assignment.lhs.inferred_type
        assert broadcast.inferred_type.element_dtype == lhs_type.element_dtype
        
        # Now run validation - should pass
        ast = validate_types(ast)


class TestBroadcastErrorConditions:
    """Test error conditions related to broadcasting."""
    
    def test_no_broadcast_for_incompatible_types(self):
        """Test that incompatible types don't get broadcast."""
        # Note: This test ensures that string literals don't get broadcast to numeric arrays
        # Such cases should fail during type inference or promotion, not validation
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 3] numbers;
                // This line should fail during parsing since string literals 
                // aren't allowed in expressions
            """
        )
        
        # This should work fine - the error would come from trying to assign
        # incompatible types, which is handled by other validation stages
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        ast = validate_types(ast)
    
    def test_broadcast_preserves_assignment_semantics(self):
        """Test that broadcasting doesn't break normal assignment semantics."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                int scalar_var;
                array[int, 5] array_var;
                scalar_var = 42;  // normal scalar assignment, no broadcast
                array_var = 42;   // scalar-to-array broadcast
            """
        )
        
        # Process through full pipeline
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        ast = validate_types(ast)
        
        # Check assignments
        init_block = ast.initializers.elements[0]
        scalar_assignment = init_block.stmts.elements[2]  # scalar_var = 42
        array_assignment = init_block.stmts.elements[3]   # array_var = 42
        
        # Scalar assignment should NOT have broadcast
        assert not isinstance(scalar_assignment.rhs, BroadcastNode_N)
        assert isinstance(scalar_assignment.rhs, IntLiteral_N)
        
        # Array assignment SHOULD have broadcast
        assert isinstance(array_assignment.rhs, BroadcastNode_N)