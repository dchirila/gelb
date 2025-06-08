#!/usr/bin/env python3

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d as minimal_gelb_program


class TestIdentifierTypeInference:
    """Test type inference for identifiers."""
    
    def test_identifier_from_constant(self):
        gelb_code = minimal_gelb_program("const int N = 32; const int double_N = N * 2;")
        ast = get_typed_ast(gelb_code)
        
        # Get the second constant definition (double_N = N * 2)
        const_stmt = ast.global_constants.stmts.elements[1]
        mul_expr = const_stmt.value
        
        # After constant resolution, N should be replaced with 32
        # But let's check if the multiplication has correct type
        assert hasattr(mul_expr, 'inferred_type')
        assert isinstance(mul_expr.inferred_type, ArrayDataType_N)
        # Check that it's 0-dimensional (scalar)
        assert len(mul_expr.inferred_type.shape.elements) == 0
        assert mul_expr.inferred_type.scalar_dtype == "int"
    
    def test_implicit_constant_Nx(self):
        # Test that Nx can be accessed from blocks via parent symbol table
        gelb_code = minimal_gelb_program(
            global_constants_content="const int SIZE = 100;",
            initializer_content="f.out[x | 0] = Nx - x;"
        )
        ast = get_typed_ast(gelb_code)
        
        # Find the subtraction expression in the assignment
        init_block = ast.initializers.elements[0]
        assign_stmt = init_block.stmts.elements[0]
        
        # The RHS should be a Sub_N expression with Nx - x
        sub_expr = assign_stmt.rhs
        assert isinstance(sub_expr, Sub_N)
        
        # Check that Nx has been resolved and has int type
        nx_identifier = sub_expr.left
        assert hasattr(nx_identifier, 'inferred_type')
        assert isinstance(nx_identifier.inferred_type, ArrayDataType_N)
        assert nx_identifier.inferred_type.scalar_dtype == "int"
    
    def test_implicit_variable_x_in_initializer(self):
        gelb_code = minimal_gelb_program(initializer_content="f.out[x | 0] = x;")
        ast = get_typed_ast(gelb_code)
        
        # Get the assignment in the initializer
        init_block = ast.initializers.elements[0]
        assign_stmt = init_block.stmts.elements[0]
        
        # The RHS should be the identifier 'x'
        x_identifier = assign_stmt.rhs
        
        # x should have int type (it's a lattice coordinate)
        assert isinstance(x_identifier, Identifier_N)
        assert hasattr(x_identifier, 'inferred_type')
        assert isinstance(x_identifier.inferred_type, ArrayDataType_N)
        assert x_identifier.inferred_type.scalar_dtype == "int"
    
    def test_array_identifier(self):
        # Test array variable declaration
        gelb_code = minimal_gelb_program(
            initializer_content="array[int, 3] vec; vec = vec; f.out[x | 0] = 0;"
        )
        ast = get_typed_ast(gelb_code)
        
        # Get the vec identifier in the assignment vec = vec
        init_block = ast.initializers.elements[0]
        # First stmt is array declaration, second is vec = vec, third is f.out assignment
        assign_stmt = init_block.stmts.elements[1]
        vec_lhs = assign_stmt.lhs
        vec_rhs = assign_stmt.rhs
        
        # Both should have array type
        assert isinstance(vec_lhs, Identifier_N)
        assert hasattr(vec_lhs, 'inferred_type')
        assert isinstance(vec_lhs.inferred_type, ArrayDataType_N)
        # scalar_dtype might be a ScalarDataType_N node
        if isinstance(vec_lhs.inferred_type.scalar_dtype, ScalarDataType_N):
            assert vec_lhs.inferred_type.scalar_dtype.scalar_dtype == "int"
        else:
            assert vec_lhs.inferred_type.scalar_dtype == "int"
        
        assert isinstance(vec_rhs, Identifier_N)
        assert hasattr(vec_rhs, 'inferred_type')
        assert isinstance(vec_rhs.inferred_type, ArrayDataType_N)
        if isinstance(vec_rhs.inferred_type.scalar_dtype, ScalarDataType_N):
            assert vec_rhs.inferred_type.scalar_dtype.scalar_dtype == "int"
        else:
            assert vec_rhs.inferred_type.scalar_dtype == "int"