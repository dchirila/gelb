#!/usr/bin/env python3
"""
Unit tests for constant folding with broadcast nodes.

Tests that BroadcastNode_N is properly handled by ConstantFoldingVisitor.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import (
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
    promote_types
)
from gelb.midware.stage2_midware import fold_constants


class TestBroadcastConstantFolding:
    """Test constant folding with broadcast nodes."""
    
    def test_constant_folding_through_broadcast(self):
        """Test that constant expressions are folded inside broadcast nodes."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 8] data;
                data = 10 + 5;  // Should fold to 15, then broadcast
            """
        )
        
        # Process through type promotion
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the broadcast node before constant folding
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        broadcast = assignment.rhs
        assert isinstance(broadcast, BroadcastNode_N)
        assert isinstance(broadcast.scalar_expr, Add_N)  # 10 + 5 not yet folded
        
        # Apply constant folding
        ast = fold_constants(ast)
        
        # After constant folding, the addition should be simplified
        assignment = init_block.stmts.elements[1]
        broadcast = assignment.rhs
        assert isinstance(broadcast, BroadcastNode_N)
        assert isinstance(broadcast.scalar_expr, IntLiteral_N)  # Folded to literal
        assert broadcast.scalar_expr.value == 15  # 10 + 5 = 15
    
    def test_broadcast_with_promoted_constant_folding(self):
        """Test constant folding with type promotion inside broadcast."""
        test_program = minimal_gelb_program_2d(
            initializer_content="""
                array[real, {2, 2}] matrix;
                matrix = 3 * 4;  // int arithmetic, promoted to real, then broadcast
            """
        )
        
        # Process through type promotion
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Apply constant folding
        ast = fold_constants(ast)
        
        # Check the result
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        broadcast = assignment.rhs
        
        assert isinstance(broadcast, BroadcastNode_N)
        # The scalar should be a type promotion wrapping a folded constant
        assert isinstance(broadcast.scalar_expr, TypePromotionNode_N)
        assert isinstance(broadcast.scalar_expr.expr, IntLiteral_N)
        assert broadcast.scalar_expr.expr.value == 12  # 3 * 4 = 12
    
    def test_broadcast_with_real_constant_folding(self):
        """Test constant folding with real arithmetic in broadcast."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[real, 5] areas;
                areas = 3.14159 * 2.0 * 2.0;  // Should fold to computed area
            """
        )
        
        # Process through midware pipeline
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        ast = fold_constants(ast)
        
        # Check the result
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        broadcast = assignment.rhs
        
        assert isinstance(broadcast, BroadcastNode_N)
        # The scalar should be folded to a single real literal
        assert isinstance(broadcast.scalar_expr, RealLiteral_N)
        # 3.14159 * 2.0 * 2.0 = 12.56636
        assert abs(broadcast.scalar_expr.value - 12.56636) < 0.00001
    
    def test_broadcast_with_bool_constant_folding(self):
        """Test constant folding with boolean logic in broadcast."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[bool, 4] results;
                results = true && false;  // Should fold to false
            """
        )
        
        # Process through midware pipeline
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        ast = fold_constants(ast)
        
        # Check the result
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        broadcast = assignment.rhs
        
        assert isinstance(broadcast, BroadcastNode_N)
        # The scalar should be folded to a single bool literal
        assert isinstance(broadcast.scalar_expr, BoolLiteral_N)
        assert broadcast.scalar_expr.value == "false"  # true && false = false
    
    def test_broadcast_no_folding_with_variables(self):
        """Test that broadcast with variables doesn't get folded."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                int x;
                array[int, 3] data;
                x = 5;
                data = x + 10;  // Can't fold because x is a variable
            """
        )
        
        # Process through midware pipeline
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        ast = fold_constants(ast)
        
        # Check the result
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[3]  # data = x + 10 (4th statement: 0=int x, 1=array[...] data, 2=x=5, 3=data=x+10)
        broadcast = assignment.rhs
        
        assert isinstance(broadcast, BroadcastNode_N)
        # The scalar should still be an Add_N (not folded)
        assert isinstance(broadcast.scalar_expr, Add_N)
        assert isinstance(broadcast.scalar_expr.left, Identifier_N)  # x
        assert isinstance(broadcast.scalar_expr.right, IntLiteral_N)  # 10
    
    def test_nested_expression_folding_in_broadcast(self):
        """Test complex nested expressions get properly folded in broadcast."""
        test_program = minimal_gelb_program_2d(
            initializer_content="""
                array[int, {3, 3}] matrix;
                matrix = (2 + 3) * 4 - 1;  // Should fold to (2+3)*4-1 = 19
            """
        )
        
        # Process through midware pipeline
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        ast = fold_constants(ast)
        
        # Check the result
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        broadcast = assignment.rhs
        
        assert isinstance(broadcast, BroadcastNode_N)
        # The entire expression should be folded to a single literal
        assert isinstance(broadcast.scalar_expr, IntLiteral_N)
        assert broadcast.scalar_expr.value == 19  # (2+3)*4-1 = 5*4-1 = 20-1 = 19