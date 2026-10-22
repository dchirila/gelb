#!/usr/bin/env python3
"""
Shared test utilities to reduce code duplication across GeLB test files.

This module provides common templates, helper functions, and test setup patterns
used throughout the test suite.
"""

import pytest
from gelb.frontend.implicit_symbols import (
    COORDINATE_SYMBOL_NAMES,
    DIMENSION_CONSTANT_NAMES,
)
from gelb.frontend.stage1_frontend import (
    get_ast,
    build_symbols_tables,
    resolve_all_constants,
    resolve_ranges,
    add_implicit_symbols,
    infer_types,
    promote_types,
    validate_types
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


def get_fully_validated_ast(gelb_code):
    """
    Helper to get AST with full validation pipeline applied including type validation.
    
    This runs the complete frontend pipeline through type validation, which includes:
    - Type inference
    - Type promotion 
    - Type validation (arithmetic operations, assignments, etc.)
    
    Args:
        gelb_code (str): GeLB source code
        
    Returns:
        Program_N: AST with full validation applied
    """
    # Set the source code in config to avoid error reporting issues
    config.GELB_SRC_RAW = gelb_code
    
    # Run the full pipeline including type validation
    ast = get_typed_ast(gelb_code)  # Up to type inference
    ast = promote_types(ast)        # Apply type promotion
    validate_types(ast)             # Apply type validation
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
        lattice f(1, 1, int, 32, false);
    }}
    initializer Init {{
        {init_stmt}
    }}
    dynamic Dyn {{
        {dyn_stmt}
    }}
    gauge Out -> (int val) {{
        {gauge_stmt}
    }}
    node_classes {{
        node_class BULK(Init, Dyn, Out);
    }}
    geometry {{
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
        lattice f(2, 9, int, {{N, N}}, {{false, false}});
    }}
    initializer Init {{
        {init_stmt}
    }}
    dynamic Dyn {{
        {dyn_stmt}
    }}
    gauge Out -> (int val) {{
        {gauge_stmt}
    }}
    node_classes {{
        node_class BULK(Init, Dyn, Out);
        node_class WALL(Init, Dyn, Out);
    }}
    geometry {{
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
        lattice f(3, 27, int, {{N, N, N}}, {{false, false, false}});
    }}
    initializer Init {{
        {init_stmt}
    }}
    dynamic Dyn {{
        {dyn_stmt}
    }}
    gauge Out -> (int val) {{
        {gauge_stmt}
    }}
    node_classes {{
        node_class BULK(Init, Dyn, Out);
        node_class WALL(Init, Dyn, Out);
    }}
    geometry {{
        {geom_stmt}
    }}
    """


def minimal_gelb_program(global_constants_content="", initializer_content="", with_array_support=False):
    """
    Alias of minimal_gelb_program_1d.
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

def get_scalar_cst_test_data():
    """Return CST test data for scalar data types parsing (for testing the grammar parser)."""
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
    return list(COORDINATE_SYMBOL_NAMES + DIMENSION_CONSTANT_NAMES)


def get_coordinate_symbols():
    """Return list of coordinate symbols (x, y, z)."""
    return list(COORDINATE_SYMBOL_NAMES)


def get_dimension_symbols():
    """Return list of dimension symbols (Nx, Ny, Nz)."""
    return list(DIMENSION_CONSTANT_NAMES)


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
          const real PI = 3.141;
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
          const real PI = 3.141;
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
        gauge PiTimesCurrentState -> (int state) {
          const real64 PI = 3.141592653589793;
          const real32 PI = 3.14159265;
          const real PI = 3.141;
          state = PI*f.in[x | 0];
        }
        """, "f"),
        
        ("gauge_block", "symbol_unknown", GeLBExSymbolUnknown, """
        gauge PiTimesCurrentState -> (int state) {
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
        """, None, "(CX \"constant definition\" (ConstantDefinitionStmt (Identifier CX) (ArrayDataType int (List )) (IntLiteral 0))) (Z \"constant definition\" (ConstantDefinitionStmt (Identifier Z) (ArrayDataType real64 (List )) (IntLiteral 123)))"),
        
        # Lattices block valid test  
        ("lattices_block", """
        lattices {
          lattice f(2, 9, real64);
          lattice g(2, 5, real64);
        }
        """, None, "(f \"lattice instance\" (LatticeInstaStmt (Identifier f) (IntLiteral 2) (IntLiteral 9) (ArrayDataType real64 (List )))) (g \"lattice instance\" (LatticeInstaStmt (Identifier g) (IntLiteral 2) (IntLiteral 5) (ArrayDataType real64 (List ))))"),
        
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
        """, "f", "(PI \"constant definition\" (ConstantDefinitionStmt (Identifier PI) (ArrayDataType real64 (List )) (RealLiteral 3.141592653589793)))"),
        
        # Initializer block valid test  
        ("initializer_block", """
        initializer SetDFsToConstant {
          const real64 PI = 3.141592653589793;
          f.out[x, y, z | :] = PI;
        }
        """, "f", "(PI \"constant definition\" (ConstantDefinitionStmt (Identifier PI) (ArrayDataType real64 (List )) (RealLiteral 3.141592653589793)))"),
        
        # Gauge block valid test
        ("gauge_block", """
        gauge PiTimesCurrentState -> (int state) {
          const real64 PI = 3.141592653589793;
          state = f.in[x | 0];
        }
        """, "f", "(PI \"constant definition\" (ConstantDefinitionStmt (Identifier PI) (ArrayDataType real64 (List )) (RealLiteral 3.141592653589793))) (state \"output variable declaration\" (VariableDeclarationStmt (Identifier state) (ArrayDataType int (List ))))"),
    ]


def get_expression_ast_test_data():
    """Return test data for expression AST building tests across all expression types."""
    return [
        # Boolean literals
        ("bool", "true_literal", "true", "(BoolLiteral true)"),
        ("bool", "false_literal", "false", "(BoolLiteral false)"),
        
        # Integer literals and arithmetic
        ("int", "zero", "0", "(IntLiteral 0)"),
        ("int", "zero_in_parens", "(0)", "(IntLiteral 0)"),
        ("int", "positive_int", "123", "(IntLiteral 123)"),
        ("int", "positive_int_in_parens", "(921)", "(IntLiteral 921)"),
        ("int", "negative_int", "-981", "(UnaryMinusExpr (IntLiteral 981))"),
        ("int", "explicitly_positive_int", "+29", "(IntLiteral 29)"),
        ("int", "addition", "123 + 321", "(Add (IntLiteral 123) (IntLiteral 321))"),
        ("int", "subtraction", "123 - 321", "(Sub (IntLiteral 123) (IntLiteral 321))"),
        ("int", "multiplication", "12 * 10", "(Mul (IntLiteral 12) (IntLiteral 10))"),
        ("int", "division", "120 / 12", "(Div (IntLiteral 120) (IntLiteral 12))"),
        ("int", "exponentiation", "2 ^ 3", "(Pow (IntLiteral 2) (IntLiteral 3))"),
        
        # Real literals and arithmetic
        ("real", "zero_dot_zero", "0.0", "(RealLiteral 0.0)"),
        ("real", "zero_dot_zero_in_parens", "(0.0)", "(RealLiteral 0.0)"),
        ("real", "simple_real", "123.456", "(RealLiteral 123.456)"),
        ("real", "real_in_parens", "(123.456)", "(RealLiteral 123.456)"),
        ("real", "negative_real", "-123.456", "(UnaryMinusExpr (RealLiteral 123.456))"),
        ("real", "explicitly_positive_real", "+123.456", "(RealLiteral 123.456)"),
        ("real", "real_addition", "123.0 + 321.0", "(Add (RealLiteral 123.0) (RealLiteral 321.0))"),
        ("real", "real_subtraction", "123.0 - 321.0", "(Sub (RealLiteral 123.0) (RealLiteral 321.0))"),
        ("real", "real_multiplication", "12.5 * 10.2", "(Mul (RealLiteral 12.5) (RealLiteral 10.2))"),
        ("real", "real_division", "120.0 / 12.0", "(Div (RealLiteral 120.0) (RealLiteral 12.0))"),
        ("real", "real_exponentiation", "2.0 ^ 3.0", "(Pow (RealLiteral 2.0) (RealLiteral 3.0))"),
        ("real", "mixed_int_real", "5 + 3.14", "(Add (IntLiteral 5) (RealLiteral 3.14))"),
        ("real", "scientific_notation_positive", "1.23e10", "(RealLiteral 12300000000.0)"),
        ("real", "scientific_notation_negative", "1.23e-10", "(RealLiteral 1.23e-10)"),
        ("real", "scientific_notation_uppercase", "1.23E10", "(RealLiteral 12300000000.0)"),
        ("real", "large_scientific", "6.022e23", "(RealLiteral 6.022e+23)"),
        ("real", "small_scientific", "1.602e-19", "(RealLiteral 1.602e-19)"),
        
        # Comparison operations
        ("comparison", "less_than", "x < y", "(Less (Identifier x) (Identifier y))"),
        ("comparison", "greater_than", "x > y", "(Greater (Identifier x) (Identifier y))"),
        ("comparison", "less_equal", "x <= y", "(LessEqual (Identifier x) (Identifier y))"),
        ("comparison", "greater_equal", "x >= y", "(GreaterEqual (Identifier x) (Identifier y))"),
        ("comparison", "equal", "x == y", "(Equal (Identifier x) (Identifier y))"),
        ("comparison", "not_equal", "x != y", "(NotEqual (Identifier x) (Identifier y))"),
        ("comparison", "literal_comparison", "5 < 10", "(Less (IntLiteral 5) (IntLiteral 10))"),
        ("comparison", "arithmetic_comparison", "x + 1 > y * 2", "(Greater (Add (Identifier x) (IntLiteral 1)) (Mul (Identifier y) (IntLiteral 2)))"),
        ("comparison", "chained_comparison", "x < y < z", "(Less (Less (Identifier x) (Identifier y)) (Identifier z))"),
        
        # Logical operations
        ("logical", "and_operation", "x && y", "(And (Identifier x) (Identifier y))"),
        ("logical", "or_operation", "x || y", "(Or (Identifier x) (Identifier y))"),
        ("logical", "not_operation", "!x", "(NotExpr (Identifier x))"),
        ("logical", "bool_and", "true && false", "(And (BoolLiteral true) (BoolLiteral false))"),
        ("logical", "bool_or", "true || false", "(Or (BoolLiteral true) (BoolLiteral false))"),
        ("logical", "bool_not", "!true", "(NotExpr (BoolLiteral true))"),
        ("logical", "complex_logical", "x && y || z", "(Or (And (Identifier x) (Identifier y)) (Identifier z))"),
        ("logical", "logical_with_comparison", "x < y && z > w", "(And (Less (Identifier x) (Identifier y)) (Greater (Identifier z) (Identifier w)))"),
        ("logical", "nested_logical_parens", "(x && y) || (z && w)", "(Or (And (Identifier x) (Identifier y)) (And (Identifier z) (Identifier w)))"),
        
        # Parentheses and precedence
        ("parens", "simple_parens", "(x)", "(Identifier x)"),
        ("parens", "nested_parens", "((x))", "(Identifier x)"),
        ("parens", "triple_nested_parens", "(((x)))", "(Identifier x)"),
        ("parens", "complex_parens", "(x + y) * z", "(Mul (Add (Identifier x) (Identifier y)) (Identifier z))"),
        ("parens", "precedence_override", "x + (y * z)", "(Add (Identifier x) (Mul (Identifier y) (Identifier z)))"),
        ("parens", "multiple_parens", "(x + y) * (z - w)", "(Mul (Add (Identifier x) (Identifier y)) (Sub (Identifier z) (Identifier w)))"),
        ("parens", "logical_parens", "(x && y) || z", "(Or (And (Identifier x) (Identifier y)) (Identifier z))"),
        ("parens", "comparison_parens", "(x < y) && (z > w)", "(And (Less (Identifier x) (Identifier y)) (Greater (Identifier z) (Identifier w)))"),
        
        # Identifiers
        ("identifier", "simple_identifier", "x", "(Identifier x)"),
        ("identifier", "identifier_in_parens", "(myVariable)", "(Identifier myVariable)"),
        ("identifier", "identifier_arithmetic", "x + y", "(Add (Identifier x) (Identifier y))"),
        ("identifier", "complex_identifier", "myLongVariableName", "(Identifier myLongVariableName)"),
        
        # Array expressions (basic cases) - these use RectSelOfArrayElems in GeLB
        ("array", "simple_array_access", "arr[i]", "(RectSelOfArrayElems (Identifier arr) (Range (Identifier i) (Identifier i)))"),
        ("array", "multi_dim_array", "matrix[i, j]", "(RectSelOfArrayElems (Identifier matrix) (Range (Identifier i) (Identifier i)) (Range (Identifier j) (Identifier j)))"),
        ("array", "array_with_arithmetic", "arr[i + 1]", "(RectSelOfArrayElems (Identifier arr) (Range (Add (Identifier i) (IntLiteral 1)) (Add (Identifier i) (IntLiteral 1))))"),
    ]


def get_expression_parse_test_data():
    """Return test data for expression parsing tests (CST) across all expression types."""
    return [
        # Comparison operations
        ("comparison", "less_than", "x < y", "(expr (expr (identifier x)) < (expr (identifier y)))"),
        ("comparison", "greater_than", "x > y", "(expr (expr (identifier x)) > (expr (identifier y)))"),
        ("comparison", "less_equal", "x <= y", "(expr (expr (identifier x)) <= (expr (identifier y)))"),
        ("comparison", "greater_equal", "x >= y", "(expr (expr (identifier x)) >= (expr (identifier y)))"),
        ("comparison", "equal", "x == y", "(expr (expr (identifier x)) == (expr (identifier y)))"),
        ("comparison", "not_equal", "x != y", "(expr (expr (identifier x)) != (expr (identifier y)))"),
        ("comparison", "numbers", "5 < 10", "(expr (expr 5) < (expr 10))"),
        ("comparison", "arithmetic_comparison", "x + 1 < y * 2", "(expr (expr (expr (identifier x)) + (expr 1)) < (expr (expr (identifier y)) * (expr 2)))"),
        ("comparison", "chained_with_logical", "x > 0 && y < 10", "(expr (expr (expr (identifier x)) > (expr 0)) && (expr (expr (identifier y)) < (expr 10)))"),
        ("comparison", "equality_with_logical", "x == 5 || y != 3", "(expr (expr (expr (identifier x)) == (expr 5)) || (expr (expr (identifier y)) != (expr 3)))"),
        
        # Logical operations
        ("logical", "and_operation", "true && false", "(expr (expr true) && (expr false))"),
        ("logical", "or_operation", "true || false", "(expr (expr true) || (expr false))"),
        ("logical", "precedence_and_or", "x && y || z", "(expr (expr (expr (identifier x)) && (expr (identifier y))) || (expr (identifier z)))"),
        ("logical", "nested_with_parens", "(a && b) || (c && d)", "(expr (expr ( (expr (expr (identifier a)) && (expr (identifier b))) )) || (expr ( (expr (expr (identifier c)) && (expr (identifier d))) )))"),
        
        # Basic expression patterns
        ("basic", "simple_addition", "x + y", "(expr (expr (identifier x)) + (expr (identifier y)))"),
        ("basic", "simple_multiplication", "a * b", "(expr (expr (identifier a)) * (expr (identifier b)))"),
        ("basic", "complex_arithmetic", "a + b * c", "(expr (expr (identifier a)) + (expr (expr (identifier b)) * (expr (identifier c))))"),
        ("basic", "parentheses", "(x + y) * z", "(expr (expr ( (expr (expr (identifier x)) + (expr (identifier y))) )) * (expr (identifier z)))"),
        ("basic", "literals", "123 + 456", "(expr (expr 123) + (expr 456))"),
        ("basic", "real_literals", "3.14 * 2.0", "(expr (expr 3.14) * (expr 2.0))"),
    ]


def get_data_type_test_data():
    """Return test data for data type testing (both scalar and array types)."""
    return [
        # Scalar data types for "data_type" rule (now create ArrayDataType_N with empty shape)
        ("scalar", "data_type", "bool", "(ArrayDataType bool (List ))"),
        ("scalar", "data_type", "int64", "(ArrayDataType int64 (List ))"),
        ("scalar", "data_type", "int32", "(ArrayDataType int32 (List ))"),
        ("scalar", "data_type", "int16", "(ArrayDataType int16 (List ))"),
        ("scalar", "data_type", "int8", "(ArrayDataType int8 (List ))"),
        ("scalar", "data_type", "int", "(ArrayDataType int (List ))"),
        ("scalar", "data_type", "real64", "(ArrayDataType real64 (List ))"),
        ("scalar", "data_type", "real32", "(ArrayDataType real32 (List ))"),
        ("scalar", "data_type", "real", "(ArrayDataType real (List ))"),
        
        # Scalar data types for "scalar_data_type" rule (same expected output)
        ("scalar", "scalar_data_type", "bool", "(ArrayDataType bool (List ))"),
        ("scalar", "scalar_data_type", "int64", "(ArrayDataType int64 (List ))"),
        ("scalar", "scalar_data_type", "int32", "(ArrayDataType int32 (List ))"),
        ("scalar", "scalar_data_type", "int16", "(ArrayDataType int16 (List ))"),
        ("scalar", "scalar_data_type", "int8", "(ArrayDataType int8 (List ))"),
        ("scalar", "scalar_data_type", "int", "(ArrayDataType int (List ))"),
        ("scalar", "scalar_data_type", "real64", "(ArrayDataType real64 (List ))"),
        ("scalar", "scalar_data_type", "real32", "(ArrayDataType real32 (List ))"),
        ("scalar", "scalar_data_type", "real", "(ArrayDataType real (List ))"),
        
        # Array data types for "data_type" rule (element_dtype is a string)
        ("array", "data_type", "array[int64, 3]", "(ArrayDataType int64 (IntLiteral 3))"),
        ("array", "data_type", "array[real64, {2, 3}]", "(ArrayDataType real64 (ArrayLiteral1D (IntLiteral 2) (IntLiteral 3)))"),
        
        # Array data types for "array_data_type" rule (same expected output)
        ("array", "array_data_type", "array[int64, 3]", "(ArrayDataType int64 (IntLiteral 3))"),
        ("array", "array_data_type", "array[real64, {2, 3}]", "(ArrayDataType real64 (ArrayLiteral1D (IntLiteral 2) (IntLiteral 3)))"),
    ]


def get_data_type_parse_test_data():
    """Return test data for data type parsing tests (CST)."""
    return [
        # Array data types parsing
        ("array", "array_data_type", "array[int64, 3]", "(array_data_type array [ (scalar_data_type (scalar_int_data_type int64)) , (array_shape (expr 3)) ])"),
        ("array", "array_data_type", "array[real64, {2, 3}]", "(array_data_type array [ (scalar_data_type (scalar_real_data_type real64)) , (array_shape (array_literal_1d { (expr 2) , (expr 3) })) ])"),
        
        # Scalar data types already handled by get_scalar_data_types() in parameterized parse test
    ]


def get_rectangular_selection_test_data():
    """Return test data for rectangular selection AST building tests."""
    return [
        # Array elements rectangular selection
        ("array", "rect_sel_of_array_elems", "my_array[x]", 
         "(RectSelOfArrayElems (Identifier my_array) (Range (Identifier x) (Identifier x)))"),
        ("array", "rect_sel_of_array_elems", "my_array[:x]", 
         "(RectSelOfArrayElems (Identifier my_array) (Range (RangePlaceholder Min) (Identifier x)))"),
        ("array", "rect_sel_of_array_elems", "my_array[x:]", 
         "(RectSelOfArrayElems (Identifier my_array) (Range (Identifier x) (RangePlaceholder Max)))"),
        ("array", "rect_sel_of_array_elems", "my_array[x-1:y+2]", 
         "(RectSelOfArrayElems (Identifier my_array) (Range (Sub (Identifier x) (IntLiteral 1)) (Add (Identifier y) (IntLiteral 2))))"),
        ("array", "rect_sel_of_array_elems", "my_array[:]", 
         "(RectSelOfArrayElems (Identifier my_array) (Range (RangePlaceholder Min) (RangePlaceholder Max)))"),
        ("array", "rect_sel_of_array_elems", "my_array[x, y]", 
         "(RectSelOfArrayElems (Identifier my_array) (Range (Identifier x) (Identifier x)) (Range (Identifier y) (Identifier y)))"),
         
        # Lattice in DFs rectangular selection
        ("lattice_in", "rect_sel_of_lattice_in_dfs", "f.in[x | 0]", 
         "(RectSelOfLatticeInDFs (Identifier f) (Range (Identifier x) (Identifier x)) (Range (IntLiteral 0) (IntLiteral 0)))"),
        ("lattice_in", "rect_sel_of_lattice_in_dfs", "g.in[x+1, y-1 | :]", 
         "(RectSelOfLatticeInDFs (Identifier g) (Range (Add (Identifier x) (IntLiteral 1)) (Add (Identifier x) (IntLiteral 1))) (Range (Sub (Identifier y) (IntLiteral 1)) (Sub (Identifier y) (IntLiteral 1))) (Range (RangePlaceholder Min) (RangePlaceholder Max)))"),
        ("lattice_in", "rect_sel_of_lattice_in_dfs", "ugly_lattice_name.in[-1+x, 3-y, z-x | 3:Q]", 
         "(RectSelOfLatticeInDFs (Identifier ugly_lattice_name) (Range (Add (UnaryMinusExpr (IntLiteral 1)) (Identifier x)) (Add (UnaryMinusExpr (IntLiteral 1)) (Identifier x))) (Range (Sub (IntLiteral 3) (Identifier y)) (Sub (IntLiteral 3) (Identifier y))) (Range (Sub (Identifier z) (Identifier x)) (Sub (Identifier z) (Identifier x))) (Range (IntLiteral 3) (Identifier Q)))"),
         
        # Lattice out DFs rectangular selection  
        ("lattice_out", "rect_sel_of_lattice_out_dfs", "f.out[x | 0]", 
         "(RectSelOfLatticeOutDFs (Identifier f) (Range (Identifier x) (Identifier x)) (Range (IntLiteral 0) (IntLiteral 0)))"),
        ("lattice_out", "rect_sel_of_lattice_out_dfs", "g.out[x+1, y-1 | :]", 
         "(RectSelOfLatticeOutDFs (Identifier g) (Range (Add (Identifier x) (IntLiteral 1)) (Add (Identifier x) (IntLiteral 1))) (Range (Sub (Identifier y) (IntLiteral 1)) (Sub (Identifier y) (IntLiteral 1))) (Range (RangePlaceholder Min) (RangePlaceholder Max)))"),
        ("lattice_out", "rect_sel_of_lattice_out_dfs", "ugly_lattice_name.out[-1+x, 3-y, z-x | 3:Q]", 
         "(RectSelOfLatticeOutDFs (Identifier ugly_lattice_name) (Range (Add (UnaryMinusExpr (IntLiteral 1)) (Identifier x)) (Add (UnaryMinusExpr (IntLiteral 1)) (Identifier x))) (Range (Sub (IntLiteral 3) (Identifier y)) (Sub (IntLiteral 3) (Identifier y))) (Range (Sub (Identifier z) (Identifier x)) (Sub (Identifier z) (Identifier x))) (Range (IntLiteral 3) (Identifier Q)))"),
    ]


def get_range_test_data():
    """Return test data for range AST building tests."""
    return [
        # Coordinate ranges
        ("coords", "coords_range", "1", "(Range (IntLiteral 1) (IntLiteral 1))"),
        ("coords", "coords_range", "23:", "(Range (IntLiteral 23) (RangePlaceholder Max))"),
        ("coords", "coords_range", ":45", "(Range (RangePlaceholder Min) (IntLiteral 45))"),
        ("coords", "coords_range", "x", "(Range (Identifier x) (Identifier x))"),
        ("coords", "coords_range", "x- 1", "(Range (Sub (Identifier x) (IntLiteral 1)) (Sub (Identifier x) (IntLiteral 1)))"),
        ("coords", "coords_range", "x- 1:", "(Range (Sub (Identifier x) (IntLiteral 1)) (RangePlaceholder Max))"),
        ("coords", "coords_range", "x:- 1", "(Range (Identifier x) (UnaryMinusExpr (IntLiteral 1)))"),
        ("coords", "coords_range", "x:x+1", "(Range (Identifier x) (Add (Identifier x) (IntLiteral 1)))"),
        ("coords", "coords_range", ":", "(Range (RangePlaceholder Min) (RangePlaceholder Max))"),
        
        # Lattice DF ranges  
        ("lattice_dfs", "lattice_dfs_range", "| :", "(Range (RangePlaceholder Min) (RangePlaceholder Max))"),
        ("lattice_dfs", "lattice_dfs_range", "|: Q", "(Range (RangePlaceholder Min) (Identifier Q))"),
        ("lattice_dfs", "lattice_dfs_range", "|2 :", "(Range (IntLiteral 2) (RangePlaceholder Max))"),
        ("lattice_dfs", "lattice_dfs_range", "|3 ", "(Range (IntLiteral 3) (IntLiteral 3))"),
        ("lattice_dfs", "lattice_dfs_range", "|/* why not a comment here? :) */4 :Q", "(Range (IntLiteral 4) (Identifier Q))"),
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
        "gauge": f"gauge Out -> (int val) {{ {content} }}",
        "node_classes": f"node_classes {{ {content} }}",
        "geometry": f"geometry {{ {content} }}"
    }
    
    return templates.get(block_type, content)
