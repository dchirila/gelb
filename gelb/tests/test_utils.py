#!/usr/bin/env python3
"""
Shared test utilities to reduce code duplication across GeLB test files.

This module provides common templates, helper functions, and test setup patterns
used throughout the test suite.
"""

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
from gelb.utils import config
from gelb.utils.exceptions import (
    GeLBExSymbolExists,
    GeLBExSymbolUnknown,
    GeLBExSymbolConstantRecursion,
    GeLBExSymbolRefBeforeDef,
    GeLBExIncorrectStagesOrdering
)


# ============================================================================
# AST Pipeline Helper Functions
# ============================================================================

def get_typed_ast(gelb_code):
    """
    Helper to get AST with full type inference pipeline applied.
    
    Args:
        gelb_code (str): GeLB source code
        
    Returns:
        Program_N: AST with types inferred for all expressions
    """
    # Set the source code in config to avoid error reporting issues
    config.GELB_SRC_RAW = gelb_code
    
    ast = get_ast("gelb_program", gelb_code)
    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    ast = infer_types(ast)
    return ast


def get_validated_ast(gelb_code):
    """
    Helper to get AST with symbol table validation applied.
    
    Args:
        gelb_code (str): GeLB source code
        
    Returns:
        Program_N: AST with symbol tables built and validated
    """
    config.GELB_SRC_RAW = gelb_code
    
    ast = get_ast("gelb_program", gelb_code)
    ast = build_symbols_tables(ast)
    return ast


def get_resolved_ast(gelb_code):
    """
    Helper to get AST with constants and ranges resolved.
    
    Args:
        gelb_code (str): GeLB source code
        
    Returns:
        Program_N: AST with constants and ranges resolved
    """
    config.GELB_SRC_RAW = gelb_code
    
    ast = get_ast("gelb_program", gelb_code)
    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    return ast


# ============================================================================
# GeLB Program Templates
# ============================================================================

def minimal_gelb_program_1d(
    global_constants_content="",
    initializer_content="",
    dynamic_content="",
    gauge_content="",
    geometry_content="",
    description="Test 1D"
):
    """
    Create a minimal valid 1D GeLB program.
    
    Args:
        global_constants_content (str): Content for global_constants block
        initializer_content (str): Content for initializer block  
        dynamic_content (str): Content for dynamic block
        gauge_content (str): Content for gauge block
        geometry_content (str): Content for geometry block
        description (str): Simulation description
        
    Returns:
        str: Complete GeLB program source code
    """
    # Default contents
    default_init = "f.out[x | 0] = 0;"
    default_dynamic = "f.out[x | 0] = f.in[x | 0];"
    default_gauge = "val = f.in[x | 0];"
    default_geometry = "nodes[:] = BULK;"
    
    # Use provided content or defaults
    init_stmt = initializer_content if initializer_content else default_init
    dyn_stmt = dynamic_content if dynamic_content else default_dynamic
    gauge_stmt = gauge_content if gauge_content else default_gauge
    geom_stmt = geometry_content if geometry_content else default_geometry
    
    # Build program
    constants_block = f"global_constants {{ {global_constants_content} }}" if global_constants_content else ""
    
    return f"""
    simulation_description("{description}");
    {constants_block}
    lattices {{
        lattice f(1, 1, int);
    }}
    initializer Init {{
        {init_stmt}
    }}
    dynamic Dyn {{
        {dyn_stmt}
    }}
    gauge Out(out = {{int val;}}) {{
        {gauge_stmt}
    }}
    node_classes {{
        node_class BULK(Init, Dyn, Out);
    }}
    geometry {{
        set_grid_size(32);
        set_grid_periodicity(false);
        {geom_stmt}
    }}
    """


def minimal_gelb_program_2d(
    geometry_content="",
    global_constants_content="",
    initializer_content="",
    dynamic_content="",
    gauge_content="",
    description="Test 2D"
):
    """
    Create a minimal valid 2D GeLB program.
    
    Args:
        global_constants_content (str): Content for global_constants block
        initializer_content (str): Content for initializer block
        dynamic_content (str): Content for dynamic block  
        gauge_content (str): Content for gauge block
        geometry_content (str): Content for geometry block
        description (str): Simulation description
        
    Returns:
        str: Complete GeLB program source code
    """
    # Default constants include N for grid size
    default_constants = "const int N = 32;"
    if global_constants_content:
        # If custom constants provided, use them (they should include N if needed)
        constants_block = global_constants_content
    else:
        constants_block = default_constants
        
    # Default contents
    default_init = "f.out[x, y | 0] = 0;"
    default_dynamic = "f.out[x, y | 0] = f.in[x, y | 0];"
    default_gauge = "val = f.in[x, y | 0];"
    default_geometry = "nodes[:, :] = BULK;"
    
    # Use provided content or defaults
    init_stmt = initializer_content if initializer_content else default_init
    dyn_stmt = dynamic_content if dynamic_content else default_dynamic
    gauge_stmt = gauge_content if gauge_content else default_gauge
    geom_stmt = geometry_content if geometry_content else default_geometry
    
    return f"""
    simulation_description("{description}");
    global_constants {{
        {constants_block}
    }}
    lattices {{
        lattice f(2, 9, int);
    }}
    initializer Init {{
        {init_stmt}
    }}
    dynamic Dyn {{
        {dyn_stmt}
    }}
    gauge Out(out = {{int val;}}) {{
        {gauge_stmt}
    }}
    node_classes {{
        node_class BULK(Init, Dyn, Out);
        node_class WALL(Init, Dyn, Out);
    }}
    geometry {{
        set_grid_size({{N, N}});
        set_grid_periodicity({{false, false}});
        {geom_stmt}
    }}
    """


def minimal_gelb_program_3d(
    global_constants_content="",
    initializer_content="",
    dynamic_content="",
    gauge_content="",
    geometry_content="",
    description="Test 3D"
):
    """
    Create a minimal valid 3D GeLB program.
    
    Args:
        global_constants_content (str): Content for global_constants block
        initializer_content (str): Content for initializer block
        dynamic_content (str): Content for dynamic block
        gauge_content (str): Content for gauge block
        geometry_content (str): Content for geometry block  
        description (str): Simulation description
        
    Returns:
        str: Complete GeLB program source code
    """
    # Default constants include N for grid size
    default_constants = "const int N = 16;"
    if global_constants_content:
        constants_block = global_constants_content
    else:
        constants_block = default_constants
        
    # Default contents
    default_init = "f.out[x, y, z | 0] = 0;"
    default_dynamic = "f.out[x, y, z | 0] = f.in[x, y, z | 0];"
    default_gauge = "val = f.in[x, y, z | 0];"
    default_geometry = "nodes[:, :, :] = BULK;"
    
    # Use provided content or defaults
    init_stmt = initializer_content if initializer_content else default_init
    dyn_stmt = dynamic_content if dynamic_content else default_dynamic
    gauge_stmt = gauge_content if gauge_content else default_gauge
    geom_stmt = geometry_content if geometry_content else default_geometry
    
    return f"""
    simulation_description("{description}");
    global_constants {{
        {constants_block}
    }}
    lattices {{
        lattice f(3, 27, int);
    }}
    initializer Init {{
        {init_stmt}
    }}
    dynamic Dyn {{
        {dyn_stmt}
    }}
    gauge Out(out = {{int val;}}) {{
        {gauge_stmt}
    }}
    node_classes {{
        node_class BULK(Init, Dyn, Out);
        node_class WALL(Init, Dyn, Out);
    }}
    geometry {{
        set_grid_size({{N, N, N}});
        set_grid_periodicity({{false, false, false}});
        {geom_stmt}
    }}
    """


# Legacy alias for backward compatibility
def minimal_gelb_program(global_constants_content="", initializer_content="", with_array_support=False):
    """
    Legacy function for backward compatibility.
    Redirects to minimal_gelb_program_1d.
    """
    return minimal_gelb_program_1d(
        global_constants_content=global_constants_content,
        initializer_content=initializer_content
    )


# ============================================================================
# CST and AST Testing Helpers  
# ============================================================================

def assert_cst_equals(test_string, expected, rule):
    """
    Helper to test CST (Concrete Syntax Tree) parsing.
    
    Args:
        test_string (str): Input string to parse
        expected (str): Expected CST string representation
        rule (str): ANTLR rule name to start parsing from
    """
    from gelb.frontend.stage1_frontend import get_cst_as_string
    result = get_cst_as_string(rule, test_string)
    assert result == expected


def assert_ast_equals(test_string, expected, rule):
    """
    Helper to test AST (Abstract Syntax Tree) building.
    
    Args:
        test_string (str): Input string to parse
        expected (str): Expected AST string representation  
        rule (str): ANTLR rule name to start parsing from
    """
    ast = get_ast(rule, test_string)
    assert str(ast) == expected


# ============================================================================
# Parameterized Test Data Generators
# ============================================================================

def get_scalar_data_types():
    """Return test data for scalar data types supported by GeLB grammar."""
    return [
        ("bool", "(scalar_data_type (scalar_bool_data_type bool))"),
        ("int64", "(scalar_data_type (scalar_int_data_type int64))"),
        ("int32", "(scalar_data_type (scalar_int_data_type int32))"),
        ("int16", "(scalar_data_type (scalar_int_data_type int16))"),
        ("int8", "(scalar_data_type (scalar_int_data_type int8))"),
        ("int", "(scalar_data_type (scalar_int_data_type int))"),
        ("real64", "(scalar_data_type (scalar_real_data_type real64))"),
        ("real32", "(scalar_data_type (scalar_real_data_type real32))"),
        ("real16", "(scalar_data_type (scalar_real_data_type real16))"),
        ("real", "(scalar_data_type (scalar_real_data_type real))"),
    ]


def get_implicit_symbols():
    """Return list of implicit symbols for testing."""
    return ["x", "y", "z", "Nx", "Ny", "Nz"]


def get_coordinate_symbols():
    """Return list of coordinate symbols (x, y, z)."""
    return ["x", "y", "z"]


def get_dimension_symbols():
    """Return list of dimension symbols (Nx, Ny, Nz)."""
    return ["Nx", "Ny", "Nz"]


def get_array_literal_parse_test_data():
    """Return test data for array literal parsing tests (CST)."""
    return [
        # 1D array literals
        ("1d", "simple", "{1, 2, 3}", 
         "(array_literal_1d { (expr 1) , (expr 2) , (expr 3) })"),
        ("1d", "with_comments", "/* comment 1*/{\n123// comment 2\n, 456//\n}",
         "(array_literal_1d { (expr 123) , (expr 456) })"),
        
        # 2D array literals  
        ("2d", "simple", "{{1, 2}, {3, 4} }",
         "(array_literal_2d { (array_literal_1d { (expr 1) , (expr 2) }) , (array_literal_1d { (expr 3) , (expr 4) }) })"),
        ("2d", "with_whitespace", "{\n{1, 2},\n{3, 4}\n}",
         "(array_literal_2d { (array_literal_1d { (expr 1) , (expr 2) }) , (array_literal_1d { (expr 3) , (expr 4) }) })"),
        
        # 3D array literals
        ("3d", "simple", "{{{1, 2}, {3, 4}}, {{5, 6}, {7, 8}}}",
         "(array_literal_3d { (array_literal_2d { (array_literal_1d { (expr 1) , (expr 2) }) , (array_literal_1d { (expr 3) , (expr 4) }) }) , (array_literal_2d { (array_literal_1d { (expr 5) , (expr 6) }) , (array_literal_1d { (expr 7) , (expr 8) }) }) })"),
        
        # 4D array literals  
        ("4d", "simple", "{{{{1,2},{3,4}},{{5,6},{7,8}}},{{{9,10},{11,12}},{{13,14},{15,16}}}}",
         "(array_literal_4d { (array_literal_3d { (array_literal_2d { (array_literal_1d { (expr 1) , (expr 2) }) , (array_literal_1d { (expr 3) , (expr 4) }) }) , (array_literal_2d { (array_literal_1d { (expr 5) , (expr 6) }) , (array_literal_1d { (expr 7) , (expr 8) }) }) }) , (array_literal_3d { (array_literal_2d { (array_literal_1d { (expr 9) , (expr 10) }) , (array_literal_1d { (expr 11) , (expr 12) }) }) , (array_literal_2d { (array_literal_1d { (expr 13) , (expr 14) }) , (array_literal_1d { (expr 15) , (expr 16) }) }) }) })"),
    ]


def get_array_literal_ast_test_data():
    """Return test data for array literal AST building tests."""
    return [
        # 1D array literals
        ("1d", "simple", "{1, 2, 3}", 
         "(ArrayLiteral1D (IntLiteral 1) (IntLiteral 2) (IntLiteral 3))"),
        ("1d", "with_comments", "/* comment 1*/{\n123// comment 2\n, 456//\n}",
         "(ArrayLiteral1D (IntLiteral 123) (IntLiteral 456))"),
        
        # 2D array literals  
        ("2d", "simple", "{{1, 2}, {3, 4} }",
         "(ArrayLiteral2D (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2)) (ArrayLiteral1D (IntLiteral 3) (IntLiteral 4)))"),
        
        # 3D array literals
        ("3d", "simple", "{{{1, 2}, {3, 4}}, {{5, 6}, {7, 8}}}",
         "(ArrayLiteral3D (ArrayLiteral2D (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2)) (ArrayLiteral1D (IntLiteral 3) (IntLiteral 4))) (ArrayLiteral2D (ArrayLiteral1D (IntLiteral 5) (IntLiteral 6)) (ArrayLiteral1D (IntLiteral 7) (IntLiteral 8))))"),
        
        # 4D array literals  
        ("4d", "simple", "{{{{1,2},{3,4}},{{5,6},{7,8}}},{{{9,10},{11,12}},{{13,14},{15,16}}}}",
         "(ArrayLiteral4D (ArrayLiteral3D (ArrayLiteral2D (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2)) (ArrayLiteral1D (IntLiteral 3) (IntLiteral 4))) (ArrayLiteral2D (ArrayLiteral1D (IntLiteral 5) (IntLiteral 6)) (ArrayLiteral1D (IntLiteral 7) (IntLiteral 8)))) (ArrayLiteral3D (ArrayLiteral2D (ArrayLiteral1D (IntLiteral 9) (IntLiteral 10)) (ArrayLiteral1D (IntLiteral 11) (IntLiteral 12))) (ArrayLiteral2D (ArrayLiteral1D (IntLiteral 13) (IntLiteral 14)) (ArrayLiteral1D (IntLiteral 15) (IntLiteral 16)))))"),
    ]


def get_binary_operator_test_data():
    """Return test data for binary operator parsing tests."""
    return [
        # Arithmetic operators
        ("add", "x + y", "(Add (Identifier x) (Identifier y))"),
        ("sub", "x - y", "(Sub (Identifier x) (Identifier y))"),
        ("mul", "x * y", "(Mul (Identifier x) (Identifier y))"),
        ("div", "x / y", "(Div (Identifier x) (Identifier y))"),
        ("pow", "x ^ y", "(Pow (Identifier x) (Identifier y))"),
        
        # Comparison operators
        ("lt", "x < y", "(Less (Identifier x) (Identifier y))"),
        ("gt", "x > y", "(Greater (Identifier x) (Identifier y))"),
        ("le", "x <= y", "(LessEqual (Identifier x) (Identifier y))"),
        ("ge", "x >= y", "(GreaterEqual (Identifier x) (Identifier y))"),
        ("eq", "x == y", "(Equal (Identifier x) (Identifier y))"),
        ("ne", "x != y", "(NotEqual (Identifier x) (Identifier y))"),
        
        # Logical operators
        ("and", "x && y", "(And (Identifier x) (Identifier y))"),
        ("or", "x || y", "(Or (Identifier x) (Identifier y))"),
    ]


def get_symbol_table_error_test_data():
    """Return test data for symbol table error tests across different block types."""
    return [
        # Global constants block tests
        ("global_constants_block", "symbol_exists", GeLBExSymbolExists, """
        global_constants {
          const array[int32, {23, 32}] NX = 32;
          const array[real64, {23, 32}] NX = 3.14;
        }
        """, None),
        
        ("global_constants_block", "symbol_unknown", GeLBExSymbolUnknown, """
        global_constants {
          const int NY = -2 * NX + NZ;
        }
        """, None),
        
        ("global_constants_block", "symbol_recursion", GeLBExSymbolConstantRecursion, """
        global_constants {
          const int NX = 123;
          const int NY = -2 * NY + NX;
        }
        """, None),
        
        ("global_constants_block", "symbol_ref_before_def", GeLBExSymbolRefBeforeDef, """
        global_constants {
          const int TWENTYFOUR = 2 * TWELVE + TWELVE;
          const int TWELVE = 12;
        }
        """, None),
        
        # Lattices block tests  
        ("lattices_block", "symbol_exists", GeLBExSymbolExists, """
        lattices {
          lattice f(3, 19, real64);
          lattice g(3, 5, real64);
          lattice f(3, 19, real64);
        }
        """, None),
        
        ("lattices_block", "symbol_unknown_d", GeLBExSymbolUnknown, """
        lattices {
          lattice f(1 + TWO, 19, real64);
        }
        """, None),
        
        ("lattices_block", "symbol_unknown_q", GeLBExSymbolUnknown, """
        lattices {
          lattice f(3, TWO + 17, real64);
        }
        """, None),
        
        # Node classes block tests
        ("node_classes_block", "symbol_exists", GeLBExSymbolExists, """
        node_classes {
          node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);
          node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);
        }
        """, None),
        
        # Dynamic block tests
        ("dynamic_block", "symbol_exists", GeLBExSymbolExists, """
        dynamic SetDFsToConstant {
          const real64 PI = 3.141592653589793;
          const real32 PI = 3.14159265;
          const real16 PI = 3.141;
          f.out[x, y, z | :] = PI;
        }
        """, "f"),
        
        ("dynamic_block", "symbol_unknown_const", GeLBExSymbolUnknown, """
        dynamic SetDFsToConstant {
          const int TWOPI = PI;
          f.out[x, y, z | :] = TWOPI;
        }
        """, "f"),
        
        ("dynamic_block", "symbol_unknown_ref", GeLBExSymbolUnknown, """
        dynamic SetDFsToConstant {
          f.out[x, y, z | :] = TWOPI;
        }
        """, "f"),
        
        ("dynamic_block", "symbol_recursion", GeLBExSymbolConstantRecursion, """
        dynamic SetDFsToConstant {
          const int NX = 123;
          const int NY = -2 * NY + NX;
          f.out[x, y, z | :] = NY;
        }
        """, "f"),
        
        # Initializer block tests
        ("initializer_block", "symbol_exists", GeLBExSymbolExists, """
        initializer SetDFsToConstant {
          const real64 PI = 3.141592653589793;
          const real32 PI = 3.14159265;
          const real16 PI = 3.141;
          f.out[x, y, z | :] = PI;
        }
        """, "f"),
        
        ("initializer_block", "symbol_unknown_const", GeLBExSymbolUnknown, """
        initializer SetDFsToConstant {
          const int TWOPI = PI;
          f.out[x, y, z | :] = TWOPI;
        }
        """, "f"),
        
        ("initializer_block", "symbol_unknown_ref", GeLBExSymbolUnknown, """
        initializer SetDFsToConstant {
          f.out[x, y, z | :] = TWOPI;
        }
        """, "f"),
        
        ("initializer_block", "symbol_unknown_var", GeLBExSymbolUnknown, """
        initializer SetDFsToConstant {
          int tutu;
          tutu = PI;
          f.out[x, y, z | :] = tutu;
        }
        """, "f"),
        
        ("initializer_block", "symbol_recursion", GeLBExSymbolConstantRecursion, """
        initializer SetDFsToConstant {
          const int NX = 123;
          const int NY = -2 * NY + NX;
          g.out[x, y, z | :] = NY;
        }
        """, "g"),
        
        # Gauge block tests
        ("gauge_block", "symbol_exists", GeLBExSymbolExists, """
        gauge PiTimesCurrentState(out = {int state;}) {
          const real64 PI = 3.141592653589793;
          const real32 PI = 3.14159265;
          const real16 PI = 3.141;
          state = PI*f.in[x | 0];
        }
        """, "f"),
        
        ("gauge_block", "symbol_unknown", GeLBExSymbolUnknown, """
        gauge PiTimesCurrentState(out = {int state;}) {
          state = PI *f.in[x | 0];
        }
        """, "f"),
    ]


def get_symbol_table_valid_test_data():
    """Return test data for valid symbol table constructions across different block types."""
    return [
        # Global constants block valid test
        ("global_constants_block", """
        global_constants {
            const int CX = 0;
            const real64 Z = 123;
        }
        """, None, "(CX \"constant definition\" (ConstantDefinitionStmt (Identifier CX) (ScalarDataType int) (IntLiteral 0))) (Z \"constant definition\" (ConstantDefinitionStmt (Identifier Z) (ScalarDataType real64) (IntLiteral 123)))"),
        
        # Lattices block valid test  
        ("lattices_block", """
        lattices {
          lattice f(2, 9, real64);
          lattice g(2, 5, real64);
        }
        """, None, "(f \"lattice instance\" (LatticeInstaStmt (Identifier f) (IntLiteral 2) (IntLiteral 9) (ScalarDataType real64))) (g \"lattice instance\" (LatticeInstaStmt (Identifier g) (IntLiteral 2) (IntLiteral 5) (ScalarDataType real64)))"),
        
        # Node classes block valid test
        ("node_classes_block", """
        node_classes {
          node_class TOP(SetDFsToZero, SetDFsToOne, CurrentState);
          node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);
        }
        """, None, "(TOP \"node class\" (NodeClassInstaStmt (Identifier TOP) (Identifier SetDFsToZero) (Identifier SetDFsToOne) (Identifier CurrentState))) (BULK \"node class\" (NodeClassInstaStmt (Identifier BULK) (Identifier SetDFsToZero) (Identifier SetDFsToOne) (Identifier CurrentState)))"),
        
        # Dynamic block valid test
        ("dynamic_block", """
        dynamic SetDFsToConstant {
          const real64 PI = 3.141592653589793;
          f.out[x, y, z | :] = PI;
        }
        """, "f", "(PI \"constant definition\" (ConstantDefinitionStmt (Identifier PI) (ScalarDataType real64) (RealLiteral 3.141592653589793)))"),
        
        # Initializer block valid test  
        ("initializer_block", """
        initializer SetDFsToConstant {
          const real64 PI = 3.141592653589793;
          f.out[x, y, z | :] = PI;
        }
        """, "f", "(PI \"constant definition\" (ConstantDefinitionStmt (Identifier PI) (ScalarDataType real64) (RealLiteral 3.141592653589793)))"),
        
        # Gauge block valid test
        ("gauge_block", """
        gauge PiTimesCurrentState(out = {int state;}) {
          const real64 PI = 3.141592653589793;
          state = f.in[x | 0];
        }
        """, "f", "(PI \"constant definition\" (ConstantDefinitionStmt (Identifier PI) (ScalarDataType real64) (RealLiteral 3.141592653589793))) (state \"output variable declaration\" (VariableDeclarationStmt (Identifier state) (ScalarDataType int)))"),
    ]


# ============================================================================
# Test Exception Helpers
# ============================================================================

def assert_symbol_unknown_error(gelb_code, expected_symbol_name=None):
    """
    Helper to assert that a GeLBExSymbolUnknown exception is raised.
    
    Args:
        gelb_code (str): GeLB code that should raise the exception
        expected_symbol_name (str, optional): Expected unknown symbol name
    """
    ast = get_ast("gelb_program", gelb_code)
    with pytest.raises(GeLBExSymbolUnknown) as exc_info:
        build_symbols_tables(ast)
    
    if expected_symbol_name:
        assert expected_symbol_name in str(exc_info.value)


def assert_symbol_redefinition_error(gelb_code, expected_symbol_name=None):
    """
    Helper to assert that a GeLBExSymbolExists exception is raised.
    
    Args:
        gelb_code (str): GeLB code that should raise the exception
        expected_symbol_name (str, optional): Expected redefined symbol name
    """
    ast = get_ast("gelb_program", gelb_code)
    with pytest.raises(GeLBExSymbolExists) as exc_info:
        build_symbols_tables(ast)
    
    if expected_symbol_name:
        assert expected_symbol_name in str(exc_info.value)


def assert_symbol_ref_before_def_error(gelb_code, expected_symbol_name=None):
    """
    Helper to assert that a GeLBExSymbolRefBeforeDef exception is raised.
    
    Args:
        gelb_code (str): GeLB code that should raise the exception
        expected_symbol_name (str, optional): Expected symbol name
    """
    ast = get_ast("gelb_program", gelb_code)
    with pytest.raises(GeLBExSymbolRefBeforeDef) as exc_info:
        build_symbols_tables(ast)
    
    if expected_symbol_name:
        assert expected_symbol_name in str(exc_info.value)


def assert_symbol_recursion_error(gelb_code, expected_symbol_name=None):
    """
    Helper to assert that a GeLBExSymbolConstantRecursion exception is raised.
    
    Args:
        gelb_code (str): GeLB code that should raise the exception
        expected_symbol_name (str, optional): Expected recursive symbol name
    """
    ast = get_ast("gelb_program", gelb_code)
    with pytest.raises(GeLBExSymbolConstantRecursion) as exc_info:
        build_symbols_tables(ast)
    
    if expected_symbol_name:
        assert expected_symbol_name in str(exc_info.value)


def assert_symbol_table_error(test_string, rule, exception_class, symbol_to_ignore="f"):
    """
    Helper to assert that a specific symbol table exception is raised.
    
    Args:
        test_string (str): Code that should raise the exception
        rule (str): ANTLR rule to parse with
        exception_class: Exception class to expect
        symbol_to_ignore (str): Symbol to ignore during testing (usually "f" for lattice)
    """
    ast = get_ast(rule, test_string)
    with pytest.raises(exception_class):
        build_symbols_tables(ast, symbol_to_ignore)


def assert_symbol_not_allowed_error(test_string, rule, expected_symbol_name=None):
    """
    Helper to assert that a GeLBExSymbolNotAllowedHere exception is raised.
    
    Args:
        test_string (str): Code that should raise the exception
        rule (str): ANTLR rule to parse with
        expected_symbol_name (str, optional): Expected disallowed symbol name
    """
    from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
    from gelb.utils.exceptions import GeLBExSymbolNotAllowedHere
    
    ast = get_ast(rule, test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def create_implicit_symbol_block_test(block_type, symbol_name, template_dict):
    """
    Create test string for implicit symbol testing in specific blocks.
    
    Args:
        block_type (str): Type of block ("global_constants", "lattices", etc.)
        symbol_name (str): Symbol to test ("x", "y", "z", "Nx", "Ny", "Nz")
        template_dict (dict): Templates for each block type
        
    Returns:
        str: Test string for the specific block and symbol combination
    """
    template = template_dict.get(block_type, "")
    return template.format(symbol=symbol_name)


# Predefined templates for implicit symbol testing
IMPLICIT_SYMBOL_TEMPLATES = {
    "global_constants": """
    global_constants { //
      const int TUTU = {symbol};
    }
    """,
    "lattices": """
    lattices {
      lattice myLattice({symbol}, 5, int);
    }
    """
}


# ============================================================================
# Block Template Helpers
# ============================================================================

def create_block_template(block_type, content):
    """
    Create a minimal block template for isolated testing.
    
    Args:
        block_type (str): Type of block ("global_constants", "lattices", etc.)
        content (str): Content for the block
        
    Returns:
        str: Minimal block template suitable for parsing
    """
    templates = {
        "global_constants": f"global_constants {{ {content} }}",
        "lattices": f"lattices {{ {content} }}",
        "initializer": f"initializer Init {{ {content} }}",
        "dynamic": f"dynamic Dyn {{ {content} }}",
        "gauge": f"gauge Out(out = {{int val;}}) {{ {content} }}",
        "node_classes": f"node_classes {{ {content} }}",
        "geometry": f"geometry {{ {content} }}"
    }
    
    return templates.get(block_type, content)