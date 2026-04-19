#!/usr/bin/env python3
"""
Unit tests for TypePromotionVisitor.

Tests implicit type promotions in various contexts.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import (
    get_typed_ast, get_fully_validated_ast,
    minimal_gelb_program_1d, minimal_gelb_program_2d,
)
from gelb.frontend.stage1_frontend import promote_types


class TestTypePromotionVisitor:
    """Test type promotion functionality."""
    
    def test_arithmetic_int_real_promotion(self):
        """Test int + real promotes int to real."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = 1 + 2.5;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # x = 1 + 2.5
        add_expr = assign_stmt.rhs
        
        # Check that left operand (1) is wrapped in TypePromotionNode_N
        assert isinstance(add_expr.left, TypePromotionNode_N)
        assert isinstance(add_expr.left.expr, IntLiteral_N)
        assert add_expr.left.expr.value == 1
        assert add_expr.left.target_type.element_dtype == "real"
        
        # Right operand (2.5) should not be promoted
        assert isinstance(add_expr.right, RealLiteral_N)
        assert add_expr.right.value == 2.5
    
    def test_arithmetic_bool_int_promotion(self):
        """Test bool + int promotes bool to int."""
        test_code = minimal_gelb_program_1d(
            initializer_content="int x; x = true + 5;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # x = true + 5
        add_expr = assign_stmt.rhs
        
        # Check that left operand (true) is wrapped in TypePromotionNode_N
        assert isinstance(add_expr.left, TypePromotionNode_N)
        assert isinstance(add_expr.left.expr, BoolLiteral_N)
        assert add_expr.left.expr.value == "true"
        assert add_expr.left.target_type.element_dtype == "int"
    
    def test_arithmetic_bool_real_promotion(self):
        """Test bool * real promotes bool to real."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = false * 3.14;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # x = false * 3.14
        mul_expr = assign_stmt.rhs
        
        # Check that left operand (false) is wrapped in TypePromotionNode_N
        assert isinstance(mul_expr.left, TypePromotionNode_N)
        assert isinstance(mul_expr.left.expr, BoolLiteral_N)
        assert mul_expr.left.expr.value == "false"
        assert mul_expr.left.target_type.element_dtype == "real"
    
    def test_comparison_promotion(self):
        """Test comparison with different types promotes to common type."""
        test_code = minimal_gelb_program_1d(
            initializer_content="bool b; b = 1 < 2.5;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # b = 1 < 2.5
        less_expr = assign_stmt.rhs
        
        # Check that left operand (1) is wrapped in TypePromotionNode_N
        assert isinstance(less_expr.left, TypePromotionNode_N)
        assert isinstance(less_expr.left.expr, IntLiteral_N)
        assert less_expr.left.expr.value == 1
        assert less_expr.left.target_type.element_dtype == "real"
    
    def test_assignment_promotion(self):
        """Test assignment promotes RHS to LHS type."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = 42;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # x = 42
        
        # Check that RHS (42) is wrapped in TypePromotionNode_N
        assert isinstance(assign_stmt.rhs, TypePromotionNode_N)
        assert isinstance(assign_stmt.rhs.expr, IntLiteral_N)
        assert assign_stmt.rhs.expr.value == 42
        assert assign_stmt.rhs.target_type.element_dtype == "real"
    
    def test_constant_definition_promotion(self):
        """Test constant definition promotes value to declared type."""
        test_code = minimal_gelb_program_1d(
            global_constants_content="const real radius = 10;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the constant definition
        const_def = ast.global_constants.stmts.elements[0]
        
        # Check that value (10) is wrapped in TypePromotionNode_N
        assert isinstance(const_def.value, TypePromotionNode_N)
        assert isinstance(const_def.value.expr, IntLiteral_N)
        assert const_def.value.expr.value == 10
        assert const_def.value.target_type.element_dtype == "real"
    
    def test_no_promotion_same_types(self):
        """Test no promotion when types already match."""
        test_code = minimal_gelb_program_1d(
            initializer_content="int x; x = 1 + 2;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # x = 1 + 2
        add_expr = assign_stmt.rhs
        
        # Neither operand should be promoted
        assert isinstance(add_expr.left, IntLiteral_N)
        assert isinstance(add_expr.right, IntLiteral_N)
    
    def test_logical_operations_no_promotion(self):
        """Test logical operations don't promote operands."""
        test_code = minimal_gelb_program_1d(
            initializer_content="bool b1; bool b2; bool b3; b3 = b1 && b2;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[3]  # b3 = b1 && b2
        and_expr = assign_stmt.rhs
        
        # Neither operand should be promoted
        assert isinstance(and_expr.left, Identifier_N)
        assert isinstance(and_expr.right, Identifier_N)
    
    def test_nested_promotion(self):
        """Test promotion in nested expressions."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = (1 + 2) * 3.14;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]
        mul_expr = assign_stmt.rhs
        
        # The (1 + 2) result should be promoted to real
        assert isinstance(mul_expr.left, TypePromotionNode_N)
        assert isinstance(mul_expr.left.expr, Add_N)
        assert mul_expr.left.target_type.element_dtype == "real"
    
    def test_array_element_assignment_promotion(self):
        """Test promotion in array element assignments."""
        test_code = minimal_gelb_program_1d(
            initializer_content="array[real, 3] data; data[0] = 1;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # data[0] = 1
        
        # RHS should be promoted to real
        assert isinstance(assign_stmt.rhs, TypePromotionNode_N)
        assert isinstance(assign_stmt.rhs.expr, IntLiteral_N)
        assert assign_stmt.rhs.expr.value == 1
        assert assign_stmt.rhs.target_type.element_dtype == "real"


class TestTypePromotionInExpressions:
    """Test type promotion in various expression contexts."""
    
    def test_complex_arithmetic_chain(self):
        """Test promotion in complex arithmetic expressions."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = 1 + 2 * 3.0 - 4;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]
        
        # The entire expression should have promotions applied
        # Structure: (1 + (2 * 3.0)) - 4
        sub_expr = assign_stmt.rhs
        assert isinstance(sub_expr, Sub_N)
        
        # Left side of subtraction: 1 + (2 * 3.0)
        add_expr = sub_expr.left
        assert isinstance(add_expr, Add_N)
        
        # 1 should be promoted to real
        assert isinstance(add_expr.left, TypePromotionNode_N)
        assert add_expr.left.target_type.element_dtype == "real"
        
        # 2 * 3.0: 2 should be promoted to real
        mul_expr = add_expr.right
        assert isinstance(mul_expr.left, TypePromotionNode_N)
        assert mul_expr.left.target_type.element_dtype == "real"
        
        # 4 should be promoted to real
        assert isinstance(sub_expr.right, TypePromotionNode_N)
        assert sub_expr.right.target_type.element_dtype == "real"
    
    def test_mixed_bool_int_real(self):
        """Test promotion with mixed bool, int, and real."""
        test_code = minimal_gelb_program_1d(
            initializer_content="real x; x = true + 1 + 2.5;"
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]
        
        # Structure: (true + 1) + 2.5
        outer_add = assign_stmt.rhs
        assert isinstance(outer_add, Add_N)
        
        # (true + 1) should result in int, then promoted to real
        inner_add = outer_add.left
        assert isinstance(inner_add, TypePromotionNode_N)
        assert inner_add.target_type.element_dtype == "real"
    
    def test_scalar_to_array_broadcast_basic(self):
        """Test basic scalar-to-array broadcasting."""
        test_code = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 5] arr;
                arr = 42;
            """
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # arr = 42
        
        # Check that RHS is a BroadcastNode_N
        assert isinstance(assign_stmt.rhs, BroadcastNode_N)
        
        # Check the scalar expression
        broadcast = assign_stmt.rhs
        assert isinstance(broadcast.scalar_expr, IntLiteral_N)
        assert broadcast.scalar_expr.value == 42
        
        # Check the target type
        assert isinstance(broadcast.target_array_type, ArrayDataType_N)
        assert broadcast.target_array_type.element_dtype == "int"
    
    def test_scalar_to_array_broadcast_with_promotion(self):
        """Test scalar-to-array broadcasting with type promotion."""
        test_code = minimal_gelb_program_2d(
            initializer_content="""
                array[real, {3, 3}] matrix;
                matrix = 1;  // int promoted to real, then broadcast
            """
        )
        ast = get_typed_ast(test_code)
        ast = promote_types(ast)
        
        # Find the assignment
        init_block = ast.initializers[0]
        assign_stmt = init_block.stmts.elements[1]  # matrix = 1
        
        # Check that RHS is a BroadcastNode_N
        assert isinstance(assign_stmt.rhs, BroadcastNode_N)
        
        # Check the scalar expression is promoted
        broadcast = assign_stmt.rhs
        assert isinstance(broadcast.scalar_expr, TypePromotionNode_N)
        assert isinstance(broadcast.scalar_expr.expr, IntLiteral_N)
        assert broadcast.scalar_expr.expr.value == 1
        assert broadcast.scalar_expr.target_type.element_dtype == "real"
        
        # Check the target type
        assert broadcast.target_array_type.element_dtype == "real"


class TestTypePromotionNodePassThrough:
    """Test that TypePromotionVisitor handles pre-existing promotion/broadcast nodes.

    When constant folding or other passes run before type promotion,
    they may insert TypePromotionNode_N or BroadcastNode_N nodes into
    the AST. The TypePromotionVisitor must traverse these without error.
    """

    def test_sqrt_in_global_constant(self):
        """sqrt() in global_constants produces a folded+promoted node
        that TypePromotionVisitor must handle."""
        code = minimal_gelb_program_1d(
            global_constants_content="const real S = sqrt(3.0);",
            initializer_content="f.out[x | 0] = 0;",
        )
        ast = get_fully_validated_ast(code)
        assert ast is not None

    def test_derived_constant_with_sqrt(self):
        """Derived constants using sqrt (common in LBM parameter setup)."""
        code = minimal_gelb_program_1d(
            global_constants_content=(
                "const real NU = 0.1;\n"
                "const real TAU = 0.5 + 3.0 * NU;\n"
                "const real S = sqrt(TAU);"
            ),
            initializer_content="f.out[x | 0] = 0;",
        )
        ast = get_fully_validated_ast(code)
        assert ast is not None

    def test_broadcast_scalar_times_array(self):
        """Scalar * array produces BroadcastNode_N that must be traversed."""
        code = minimal_gelb_program_1d(
            global_constants_content="const array[real, 3] V = {1.0, 2.0, 3.0};",
            initializer_content="array[real, 3] R = 2.0 * V;\nf.out[x | 0] = 0;",
        )
        ast = get_fully_validated_ast(code)
        assert ast is not None

    def test_int_broadcast_to_real_array(self):
        """int * real_array triggers both promotion and broadcast."""
        code = minimal_gelb_program_1d(
            global_constants_content="const array[real, 3] V = {1.0, 2.0, 3.0};",
            initializer_content="array[real, 3] R = 2 * V;\nf.out[x | 0] = 0;",
        )
        ast = get_fully_validated_ast(code)
        assert ast is not None