#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import (
    get_ast,
    build_symbols_tables,
    resolve_all_constants,
    resolve_ranges,
    add_implicit_symbols,
    infer_types
)
from gelb.gelb_ast.ASTNodes import *


def get_typed_ast(gelb_code):
    """Helper to get AST with types inferred."""
    ast = get_ast("gelb_program", gelb_code)
    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    ast = infer_types(ast)
    return ast


def minimal_gelb_program(global_constants_content=""):
    """Create a minimal valid GeLB program with the given global constants."""
    return f"""
    simulation_description("Test");
    {f"global_constants {{ {global_constants_content} }}" if global_constants_content else ""}
    lattices {{
        lattice f(1, 1, int);
    }}
    initializer Init {{
        f.out[x | 0] = 0;
    }}
    dynamic Dyn {{
        f.out[x | 0] = f.in[x | 0];
    }}
    gauge Out(out = {{int val;}}) {{
        val = f.in[x | 0];
    }}
    node_classes {{
        node_class BULK(Init, Dyn, Out);
    }}
    geometry {{
        set_grid_size(32);
        set_grid_periodicity(false);
        nodes[:] = BULK;
    }}
    """


class TestLiteralTypeInference:
    """Test type inference for literal expressions."""
    
    def test_int_literal(self):
        gelb_code = minimal_gelb_program("const int x = 42;")
        ast = get_typed_ast(gelb_code)
        
        # Get the constant definition
        const_stmt = ast.global_constants.stmts.elements[0]
        literal = const_stmt.value
        
        # Check that type was inferred
        assert hasattr(literal, 'inferred_type')
        assert isinstance(literal.inferred_type, ScalarDataType_N)
        assert literal.inferred_type.scalar_dtype == "int"
    
    def test_real_literal(self):
        gelb_code = minimal_gelb_program("const real pi = 3.14159;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        literal = const_stmt.value
        
        assert hasattr(literal, 'inferred_type')
        assert isinstance(literal.inferred_type, ScalarDataType_N)
        assert literal.inferred_type.scalar_dtype == "real"
    
    def test_bool_literal_true(self):
        gelb_code = minimal_gelb_program("const bool flag = true;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        literal = const_stmt.value
        
        assert hasattr(literal, 'inferred_type')
        assert isinstance(literal.inferred_type, ScalarDataType_N)
        assert literal.inferred_type.scalar_dtype == "bool"
    
    def test_bool_literal_false(self):
        gelb_code = minimal_gelb_program("const bool flag = false;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        literal = const_stmt.value
        
        assert hasattr(literal, 'inferred_type')
        assert isinstance(literal.inferred_type, ScalarDataType_N)
        assert literal.inferred_type.scalar_dtype == "bool"
    
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