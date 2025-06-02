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


class TestBinaryOperationTypeInference:
    """Test type inference for binary operations."""
    
    def test_int_plus_int(self):
        gelb_code = minimal_gelb_program("const int result = 1 + 2;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        add_expr = const_stmt.value
        
        # Check that the Add_N node has inferred type
        assert hasattr(add_expr, 'inferred_type')
        assert isinstance(add_expr.inferred_type, ScalarDataType_N)
        assert add_expr.inferred_type.scalar_dtype == "int"
    
    def test_real_plus_real(self):
        gelb_code = minimal_gelb_program("const real result = 1.5 + 2.5;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        add_expr = const_stmt.value
        
        assert hasattr(add_expr, 'inferred_type')
        assert isinstance(add_expr.inferred_type, ScalarDataType_N)
        assert add_expr.inferred_type.scalar_dtype == "real"
    
    def test_int_plus_real(self):
        gelb_code = minimal_gelb_program("const real result = 1 + 2.5;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        add_expr = const_stmt.value
        
        # Mixed int + real should promote to real
        assert hasattr(add_expr, 'inferred_type')
        assert isinstance(add_expr.inferred_type, ScalarDataType_N)
        assert add_expr.inferred_type.scalar_dtype == "real"
    
    def test_multiplication(self):
        gelb_code = minimal_gelb_program("const int result = 3 * 4;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        mul_expr = const_stmt.value
        
        assert hasattr(mul_expr, 'inferred_type')
        assert isinstance(mul_expr.inferred_type, ScalarDataType_N)
        assert mul_expr.inferred_type.scalar_dtype == "int"
    
    def test_division(self):
        gelb_code = minimal_gelb_program("const real result = 10.0 / 3.0;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        div_expr = const_stmt.value
        
        assert hasattr(div_expr, 'inferred_type')
        assert isinstance(div_expr.inferred_type, ScalarDataType_N)
        assert div_expr.inferred_type.scalar_dtype == "real"
    
    def test_power(self):
        gelb_code = minimal_gelb_program("const int result = 2^3;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        pow_expr = const_stmt.value
        
        assert hasattr(pow_expr, 'inferred_type')
        assert isinstance(pow_expr.inferred_type, ScalarDataType_N)
        assert pow_expr.inferred_type.scalar_dtype == "int"
    
    def test_comparison_less(self):
        gelb_code = minimal_gelb_program("const bool result = 1 < 2;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        less_expr = const_stmt.value
        
        # Comparison operations always return bool
        assert hasattr(less_expr, 'inferred_type')
        assert isinstance(less_expr.inferred_type, ScalarDataType_N)
        assert less_expr.inferred_type.scalar_dtype == "bool"
    
    def test_comparison_equal(self):
        gelb_code = minimal_gelb_program("const bool result = 3.14 == 3.14;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        eq_expr = const_stmt.value
        
        assert hasattr(eq_expr, 'inferred_type')
        assert isinstance(eq_expr.inferred_type, ScalarDataType_N)
        assert eq_expr.inferred_type.scalar_dtype == "bool"
    
    def test_logical_and(self):
        gelb_code = minimal_gelb_program("const bool result = true && false;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        and_expr = const_stmt.value
        
        assert hasattr(and_expr, 'inferred_type')
        assert isinstance(and_expr.inferred_type, ScalarDataType_N)
        assert and_expr.inferred_type.scalar_dtype == "bool"
    
    def test_logical_or(self):
        gelb_code = minimal_gelb_program("const bool result = true || false;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        or_expr = const_stmt.value
        
        assert hasattr(or_expr, 'inferred_type')
        assert isinstance(or_expr.inferred_type, ScalarDataType_N)
        assert or_expr.inferred_type.scalar_dtype == "bool"
    
    def test_complex_expression(self):
        gelb_code = minimal_gelb_program("const real result = (1 + 2) * 3.5 / 2.0;")
        ast = get_typed_ast(gelb_code)
        
        const_stmt = ast.global_constants.stmts.elements[0]
        expr = const_stmt.value
        
        # The top-level expression should be real (due to 3.5 and 2.0)
        assert hasattr(expr, 'inferred_type')
        assert isinstance(expr.inferred_type, ScalarDataType_N)
        assert expr.inferred_type.scalar_dtype == "real"