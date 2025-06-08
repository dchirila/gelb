#!/usr/bin/env python3

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.unit.type_inference.type_inference_test_utils import get_typed_ast, minimal_gelb_program_1d as minimal_gelb_program


class TestLiteralTypeInference:
    """Test type inference for literal expressions."""
    
    def test_int_literal(self):
        gelb_code = minimal_gelb_program("const int x = 42;")
        ast = get_typed_ast(gelb_code)
        
        # Get the constant definition
        const_stmt = ast.global_constants.stmts.elements[0]
        literal = const_stmt.value
        
        # Check that type was inferred as 0-dimensional array
        assert hasattr(literal, 'inferred_type')
        assert isinstance(literal.inferred_type, ArrayDataType_N)
        assert literal.inferred_type.scalar_dtype == "int"
        # Check that it's 0-dimensional (scalar)
        assert len(literal.inferred_type.shape.elements) == 0
    
    def test_real_literal(self):
        gelb_code = minimal_gelb_program("const real pi = 3.14159;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        literal = const_stmt.value
        
        assert hasattr(literal, 'inferred_type')
        assert isinstance(literal.inferred_type, ArrayDataType_N)
        assert literal.inferred_type.scalar_dtype == "real"
        # Check that it's 0-dimensional (scalar)
        assert len(literal.inferred_type.shape.elements) == 0
    
    def test_bool_literal_true(self):
        gelb_code = minimal_gelb_program("const bool flag = true;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        literal = const_stmt.value
        
        assert hasattr(literal, 'inferred_type')
        assert isinstance(literal.inferred_type, ArrayDataType_N)
        assert literal.inferred_type.scalar_dtype == "bool"
        # Check that it's 0-dimensional (scalar)
        assert len(literal.inferred_type.shape.elements) == 0
    
    def test_bool_literal_false(self):
        gelb_code = minimal_gelb_program("const bool flag = false;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        literal = const_stmt.value
        
        assert hasattr(literal, 'inferred_type')
        assert isinstance(literal.inferred_type, ArrayDataType_N)
        assert literal.inferred_type.scalar_dtype == "bool"
        # Check that it's 0-dimensional (scalar)
        assert len(literal.inferred_type.shape.elements) == 0
    
    def test_array_1d_literal(self):
        gelb_code = minimal_gelb_program("const array[int, 3] vec = {1, 2, 3};")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        literal = const_stmt.value
        
        assert hasattr(literal, 'inferred_type')
        assert isinstance(literal.inferred_type, ArrayDataType_N)
        assert literal.inferred_type.scalar_dtype == "int"
        
        # Check shape
        shape = literal.inferred_type.shape
        assert isinstance(shape, IntLiteral_N)
        assert shape.value == 3
    
    def test_array_2d_literal(self):
        gelb_code = minimal_gelb_program("const array[real, {2, 3}] mat = {{1.0, 2.0, 3.0}, {4.0, 5.0, 6.0}};")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        literal = const_stmt.value
        
        assert hasattr(literal, 'inferred_type')
        assert isinstance(literal.inferred_type, ArrayDataType_N)
        assert literal.inferred_type.scalar_dtype == "real"
        
        # Check shape
        shape = literal.inferred_type.shape
        assert isinstance(shape, Array1DLiteral_N)
        assert len(shape.value.elements) == 2
        assert shape.value.elements[0].value == 2
        assert shape.value.elements[1].value == 3