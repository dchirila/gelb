#!/usr/bin/env python3

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
from gelb.utils.CodeRange import CodeRange


class TestConstantFoldingDirect:
    """Direct tests of constant folding visitor without full compilation pipeline."""
    
    def test_addition_folding_direct(self):
        """Test folding addition with direct AST construction."""
        # Create a simple addition: 5 + 3
        code_range = CodeRange(1, 1, 1, 5)
        left = IntLiteral_N(code_range, 5)
        right = IntLiteral_N(code_range, 3)
        add_node = Add_N(code_range, left, right)
        
        # Apply constant folding
        folder = ConstantFoldingVisitor()
        result = folder.visit(add_node, None)
        
        # Should be folded to IntLiteral_N(8)
        assert isinstance(result, IntLiteral_N)
        assert result.value == 8
    
    def test_subtraction_to_zero_direct(self):
        """Test folding subtraction that results in zero."""
        code_range = CodeRange(1, 1, 1, 5)
        left = IntLiteral_N(code_range, 5)
        right = IntLiteral_N(code_range, 5)
        sub_node = Sub_N(code_range, left, right)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(sub_node, None)
        
        # Should be folded to IntLiteral_N(0) - important for division by zero detection
        assert isinstance(result, IntLiteral_N)
        assert result.value == 0
    
    def test_multiplication_folding_direct(self):
        """Test folding multiplication with direct AST construction."""
        code_range = CodeRange(1, 1, 1, 5)
        left = IntLiteral_N(code_range, 4)
        right = IntLiteral_N(code_range, 7)
        mul_node = Mul_N(code_range, left, right)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(mul_node, None)
        
        assert isinstance(result, IntLiteral_N)
        assert result.value == 28
    
    def test_division_folding_direct(self):
        """Test folding division with direct AST construction."""
        code_range = CodeRange(1, 1, 1, 5)
        left = IntLiteral_N(code_range, 15)
        right = IntLiteral_N(code_range, 3)
        div_node = Div_N(code_range, left, right)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(div_node, None)
        
        # Integer division in Python returns float
        assert isinstance(result, RealLiteral_N)
        assert result.value == 5.0
    
    def test_division_by_zero_not_folded_direct(self):
        """Test that division by zero is not folded."""
        code_range = CodeRange(1, 1, 1, 5)
        left = IntLiteral_N(code_range, 1)
        right = IntLiteral_N(code_range, 0)
        div_node = Div_N(code_range, left, right)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(div_node, None)
        
        # Should remain as Div_N (not folded due to ZeroDivisionError)
        assert isinstance(result, Div_N)
        assert isinstance(result.left, IntLiteral_N)
        assert isinstance(result.right, IntLiteral_N)
        assert result.left.value == 1
        assert result.right.value == 0
    
    def test_comparison_folding_direct(self):
        """Test folding comparison operations."""
        code_range = CodeRange(1, 1, 1, 5)
        left = IntLiteral_N(code_range, 5)
        right = IntLiteral_N(code_range, 3)
        less_node = Less_N(code_range, left, right)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(less_node, None)
        
        assert isinstance(result, BoolLiteral_N)
        assert result.value == 'false'  # 5 < 3 is false
    
    def test_logical_and_folding_direct(self):
        """Test folding logical AND operations."""
        code_range = CodeRange(1, 1, 1, 5)
        left = BoolLiteral_N(code_range, 'true')
        right = BoolLiteral_N(code_range, 'false')
        and_node = And_N(code_range, left, right)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(and_node, None)
        
        assert isinstance(result, BoolLiteral_N)
        assert result.value == 'false'  # true && false is false
    
    def test_unary_minus_folding_direct(self):
        """Test folding unary minus operations."""
        code_range = CodeRange(1, 1, 1, 5)
        operand = IntLiteral_N(code_range, 42)
        minus_node = UnaryMinusExpr_N(code_range, operand)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(minus_node, None)
        
        assert isinstance(result, IntLiteral_N)
        assert result.value == -42
    
    def test_nested_arithmetic_folding_direct(self):
        """Test folding nested arithmetic expressions."""
        code_range = CodeRange(1, 1, 1, 5)
        
        # Create (2 + 3) * (4 - 1)
        # Inner expressions
        add_left = IntLiteral_N(code_range, 2)
        add_right = IntLiteral_N(code_range, 3)
        add_node = Add_N(code_range, add_left, add_right)
        
        sub_left = IntLiteral_N(code_range, 4)
        sub_right = IntLiteral_N(code_range, 1)
        sub_node = Sub_N(code_range, sub_left, sub_right)
        
        # Outer multiplication
        mul_node = Mul_N(code_range, add_node, sub_node)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(mul_node, None)
        
        # (2+3) * (4-1) = 5 * 3 = 15
        assert isinstance(result, IntLiteral_N)
        assert result.value == 15
    
    def test_mixed_types_folding_direct(self):
        """Test folding with mixed integer and real types."""
        code_range = CodeRange(1, 1, 1, 5)
        left = IntLiteral_N(code_range, 5)
        right = RealLiteral_N(code_range, 2.5)
        add_node = Add_N(code_range, left, right)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(add_node, None)
        
        assert isinstance(result, RealLiteral_N)
        assert result.value == 7.5
    
    def test_non_constant_not_folded_direct(self):
        """Test that non-constant expressions are not folded."""
        code_range = CodeRange(1, 1, 1, 5)
        left = IntLiteral_N(code_range, 5)
        right = Identifier_N(code_range, "x")  # Variable, not constant
        add_node = Add_N(code_range, left, right)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(add_node, None)
        
        # Should remain as Add_N (not folded)
        assert isinstance(result, Add_N)
        assert isinstance(result.left, IntLiteral_N)
        assert isinstance(result.right, Identifier_N)


class TestConstantFoldingProgram:
    """Test constant folding on minimal program structures."""
    
    def test_constant_definition_folding(self):
        """Test folding in constant definition statement."""
        code_range = CodeRange(1, 1, 1, 5)
        
        # Create const int RESULT = 5 + 3;
        data_type = ScalarDataType_N(code_range, "int")
        name = Identifier_N(code_range, "RESULT")
        
        # Value: 5 + 3
        left = IntLiteral_N(code_range, 5)
        right = IntLiteral_N(code_range, 3)
        value = Add_N(code_range, left, right)
        
        const_stmt = ConstantDefinitionStmt_N(code_range, data_type, name, value)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(const_stmt, None)
        
        # Value should be folded to 8
        assert isinstance(result, ConstantDefinitionStmt_N)
        assert isinstance(result.value, IntLiteral_N)
        assert result.value.value == 8
    
    def test_assignment_statement_folding(self):
        """Test folding in assignment statements."""
        code_range = CodeRange(1, 1, 1, 5)
        
        # Create x = 10 - 5;
        lhs = Identifier_N(code_range, "x")
        
        # RHS: 10 - 5
        left = IntLiteral_N(code_range, 10)
        right = IntLiteral_N(code_range, 5)
        rhs = Sub_N(code_range, left, right)
        
        assignment = VariableAssignmentStmt_N(code_range, lhs, rhs)
        
        folder = ConstantFoldingVisitor()
        result = folder.visit(assignment, None)
        
        # RHS should be folded to 5
        assert isinstance(result, VariableAssignmentStmt_N)
        assert isinstance(result.rhs, IntLiteral_N)
        assert result.rhs.value == 5