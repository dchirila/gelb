#!/usr/bin/env python3
"""
Unit tests for scalar-to-array broadcasting functionality.

Tests the BroadcastNode_N AST node and its integration with the type system.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import (
    get_typed_ast,
    minimal_gelb_program_1d,
    minimal_gelb_program_2d,
    minimal_gelb_program_3d
)
from gelb.frontend.stage1_frontend import (
    get_ast,
    build_symbols_tables,
    add_implicit_symbols,
    resolve_all_constants,
    resolve_ranges,
    infer_types,
    promote_types
)


class TestScalarToArrayBroadcasting:
    """Test scalar-to-array broadcasting in assignments."""
    
    def test_broadcast_int_to_real_array_1d(self):
        """Test broadcasting integer scalar to 1D real array."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[real, 5] vec;
                vec = 42;
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]  # vec = 42;
        
        # Check that RHS is a BroadcastNode
        assert isinstance(assignment.rhs, BroadcastNode_N)
        
        # Check the broadcast node structure
        broadcast = assignment.rhs
        assert isinstance(broadcast.scalar_expr, TypePromotionNode_N)  # int->real promotion
        assert isinstance(broadcast.scalar_expr.expr, IntLiteral_N)
        assert broadcast.scalar_expr.expr.value == 42
        
        # Check target array type
        assert isinstance(broadcast.target_array_type, ArrayDataType_N)
        assert broadcast.target_array_type.element_dtype == "real"
        assert isinstance(broadcast.target_array_type.shape, IntLiteral_N)
        assert broadcast.target_array_type.shape.value == 5
    
    def test_broadcast_real_to_real_array_2d(self):
        """Test broadcasting real scalar to 2D real array."""
        test_program = minimal_gelb_program_2d(
            initializer_content="""
                array[real, {3, 4}] matrix;
                matrix = 3.14;
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]  # matrix = 3.14;
        
        # Check that RHS is a BroadcastNode
        assert isinstance(assignment.rhs, BroadcastNode_N)
        
        # Check the broadcast node structure (no promotion needed for real->real)
        broadcast = assignment.rhs
        assert isinstance(broadcast.scalar_expr, RealLiteral_N)
        assert broadcast.scalar_expr.value == 3.14
        
        # Check target array type
        assert isinstance(broadcast.target_array_type, ArrayDataType_N)
        assert broadcast.target_array_type.element_dtype == "real"
        assert isinstance(broadcast.target_array_type.shape, Array1DLiteral_N)
        shape_elements = broadcast.target_array_type.shape.value.elements
        assert len(shape_elements) == 2
        assert shape_elements[0].value == 3
        assert shape_elements[1].value == 4
    
    def test_broadcast_bool_to_bool_array_3d(self):
        """Test broadcasting boolean scalar to 3D bool array."""
        test_program = minimal_gelb_program_3d(
            initializer_content="""
                array[bool, {2, 2, 2}] flags;
                flags = true;
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]  # flags = true;
        
        # Check that RHS is a BroadcastNode
        assert isinstance(assignment.rhs, BroadcastNode_N)
        
        # Check the broadcast node structure
        broadcast = assignment.rhs
        assert isinstance(broadcast.scalar_expr, BoolLiteral_N)
        assert broadcast.scalar_expr.value == "true"
        
        # Check target array type
        assert isinstance(broadcast.target_array_type, ArrayDataType_N)
        assert broadcast.target_array_type.element_dtype == "bool"
    
    def test_broadcast_with_type_promotion_bool_to_int(self):
        """Test broadcasting with type promotion from bool to int array."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 10] counts;
                counts = true;  // bool promoted to int, then broadcast
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        
        # Check that RHS is a BroadcastNode
        assert isinstance(assignment.rhs, BroadcastNode_N)
        
        # Check the broadcast node has a promotion inside
        broadcast = assignment.rhs
        assert isinstance(broadcast.scalar_expr, TypePromotionNode_N)
        assert isinstance(broadcast.scalar_expr.expr, BoolLiteral_N)
        assert broadcast.scalar_expr.target_type.element_dtype == "int"
    
    def test_no_broadcast_for_array_to_array(self):
        """Test that array-to-array assignment doesn't create broadcast nodes."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 3] src;
                array[int, 3] dst;
                src[0] = 1;
                src[1] = 2;
                src[2] = 3;
                dst = src;  // array-to-array, no broadcast
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the last assignment statement (dst = src)
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[-1]
        
        # Check that RHS is NOT a BroadcastNode
        assert not isinstance(assignment.rhs, BroadcastNode_N)
        assert isinstance(assignment.rhs, Identifier_N)
        assert assignment.rhs.name == "src"
    
    def test_broadcast_to_array_element_selection(self):
        """Test that single element assignment doesn't create broadcast nodes."""
        test_program = minimal_gelb_program_2d(
            initializer_content="""
                array[real, {2, 3}] matrix;
                matrix[0, 0] = 1.5;  // single element, no broadcast
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        
        # Check that RHS is NOT a BroadcastNode (single element assignment)
        assert not isinstance(assignment.rhs, BroadcastNode_N)
        assert isinstance(assignment.rhs, RealLiteral_N)
    
    def test_broadcast_with_constant_expression(self):
        """Test broadcasting a constant expression to an array."""
        test_program = minimal_gelb_program_1d(
            global_constants_content="""
                const int SIZE = 5;
                const real PI = 3.14159;
            """,
            initializer_content="""
                array[real, SIZE] values;
                values = 2 * PI;  // constant expression broadcast
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        
        # Check that RHS is a BroadcastNode
        assert isinstance(assignment.rhs, BroadcastNode_N)
        
        # The scalar expression should be the multiplication
        broadcast = assignment.rhs
        assert isinstance(broadcast.scalar_expr, Mul_N)
    
    def test_broadcast_node_string_representation(self):
        """Test the string representation of BroadcastNode_N."""
        # Create a broadcast node manually
        scalar = IntLiteral_N(None, 42)
        target_type = ArrayDataType_N(None, "int", IntLiteral_N(None, 5))
        broadcast = BroadcastNode_N(None, scalar, target_type)
        
        # Check string representation
        assert str(broadcast) == "(Broadcast (IntLiteral 42) -> (ArrayDataType int (IntLiteral 5)))"
    
    def test_broadcast_node_children(self):
        """Test that BroadcastNode_N properly reports its children."""
        # Create a broadcast node manually
        scalar = IntLiteral_N(None, 42)
        target_type = ArrayDataType_N(None, "int", IntLiteral_N(None, 5))
        broadcast = BroadcastNode_N(None, scalar, target_type)
        
        # Check children
        children = broadcast.get_children()
        assert scalar in children
        assert target_type in children
        assert len(children) == 2


class TestBroadcastingEdgeCases:
    """Test edge cases and error conditions for broadcasting."""
    
    def test_nested_arrays_no_broadcast(self):
        """Test that nested array types don't support broadcasting."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[array[int, 3], 2] nested;
                // This should fail during parsing, not reach broadcasting
            """
        )
        
        # This should fail during parsing since nested arrays aren't supported
        with pytest.raises(Exception):
            ast = get_ast("gelb_program", test_program)
    
    def test_broadcast_preserves_inferred_type(self):
        """Test that broadcast nodes have correct inferred type."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[real, 8] data;
                data = 0;
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        
        # Check broadcast node's inferred type
        broadcast = assignment.rhs
        assert hasattr(broadcast, 'inferred_type')
        assert isinstance(broadcast.inferred_type, ArrayDataType_N)
        assert broadcast.inferred_type.element_dtype == "real"
        assert isinstance(broadcast.inferred_type.shape, IntLiteral_N)
        assert broadcast.inferred_type.shape.value == 8