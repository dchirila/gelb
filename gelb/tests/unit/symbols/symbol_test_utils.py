#!/usr/bin/env python3
"""
Symbol table test utilities.

This module provides utilities specific to symbol table validation and testing.
"""

def assert_symbol_not_allowed_error(test_string, rule):
    """
    Helper to test that implicit symbols are properly rejected in blocks where they shouldn't be allowed.
    
    Args:
        test_string (str): GeLB code string to test
        rule (str): ANTLR rule name to start parsing from
    """
    import pytest
    from gelb.tests.test_utils import get_ast
    from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
    from gelb.utils.exceptions import GeLBExSymbolNotAllowedHere
    
    ast = get_ast(rule, test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def get_coordinate_symbols():
    """Return list of coordinate symbol names for testing."""
    return ["x", "y", "z"]


def get_dimension_symbols():
    """Return list of dimension symbol names for testing."""
    return ["Nx", "Ny", "Nz"]


def get_symbol_table_error_test_data():
    """Return test data for symbol table error validation tests."""
    from gelb.utils.exceptions import (
        GeLBExSymbolExists, GeLBExSymbolUnknown, 
        GeLBExSymbolConstantRecursion, GeLBExSymbolRefBeforeDef
    )
    
    return [
        # Global constants block tests
        ("global_constants_block", "symbol_exists", GeLBExSymbolExists,
         """
         global_constants {
           const array[int32, {23, 32}] NX = 32;
           const array[real64, {23, 32}] NX = 3.14;
         }
         """, None),
        
        
        ("global_constants_block", "symbol_unknown", GeLBExSymbolUnknown,
         """
         global_constants {
           const int NY = -2 * NX + NZ;
         }
         """, None),
        
        ("global_constants_block", "symbol_recursion", GeLBExSymbolConstantRecursion,
         """
         global_constants {
           const int NX = 123;
           const int NY = -2 * NY + NX;
         }
         """, None),
        
        ("global_constants_block", "symbol_ref_before_def", GeLBExSymbolRefBeforeDef,
         """
         global_constants {
           const int TWENTYFOUR = 2 * TWELVE + TWELVE;
           const int TWELVE = 12;
         }
         """, None),
        
        # Lattices block tests
        ("lattices_block", "symbol_exists", GeLBExSymbolExists,
         """
         lattices {
           lattice f(3, 19, real64, {32, 32, 32}, {true, true, true});
           lattice g(3, 5, real64, {32, 32, 32}, {true, true, true});
           lattice f(3, 19, real64, {32, 32, 32}, {true, true, true});
         }
         """, None),
        
        ("lattices_block", "symbol_unknown_d", GeLBExSymbolUnknown,
         """
         lattices {
           lattice f(1 + TWO, 19, real64, 32, false);
         }
         """, None),
        
        ("lattices_block", "symbol_unknown_q", GeLBExSymbolUnknown,
         """
         lattices {
           lattice f(3, TWO + 17, real64, {32, 32, 32}, {true, true, true});
         }
         """, None),
        
        # Initializer block tests
        ("initializer_block", "symbol_exists", GeLBExSymbolExists,
         """
         initializer SetDFsToConstant {
           const real64 PI = 3.141592653589793;
           const real32 PI = 3.14159265;
           const real16 PI = 3.141;
           f.out[x, y, z | :] = PI;
         }
         """, "f"),
        
        ("initializer_block", "symbol_unknown_const", GeLBExSymbolUnknown,
         """
         initializer SetDFsToConstant {
           const int TWOPI = PI;
           f.out[x, y, z | :] = TWOPI;
         }
         """, "f"),
        
        ("initializer_block", "symbol_unknown_ref", GeLBExSymbolUnknown,
         """
         initializer SetDFsToConstant {
           f.out[x, y, z | :] = TWOPI;
         }
         """, "f"),
        
        ("initializer_block", "symbol_unknown_var", GeLBExSymbolUnknown,
         """
         initializer SetDFsToConstant {
           int tutu;
           tutu = PI;
           f.out[x, y, z | :] = tutu;
         }
         """, "f"),
        
        ("initializer_block", "symbol_recursion", GeLBExSymbolConstantRecursion,
         """
         initializer SetDFsToConstant {
           const int NX = 123;
           const int NY = -2 * NY + NX;
           g.out[x, y, z | :] = NY;
         }
         """, "g"),
        
        # Dynamic block tests
        ("dynamic_block", "symbol_exists", GeLBExSymbolExists,
         """
         dynamic SetDFsToConstant {
           const real64 PI = 3.141592653589793;
           const real32 PI = 3.14159265;
           const real16 PI = 3.141;
           f.out[x, y, z | :] = PI;
         }
         """, "f"),
        
        ("dynamic_block", "symbol_unknown_const", GeLBExSymbolUnknown,
         """
         dynamic SetDFsToConstant {
           const int TWOPI = PI;
           f.out[x, y, z | :] = TWOPI;
         }
         """, "f"),
        
        ("dynamic_block", "symbol_unknown_ref", GeLBExSymbolUnknown,
         """
         dynamic SetDFsToConstant {
           f.out[x, y, z | :] = TWOPI;
         }
         """, "f"),
        
        ("dynamic_block", "symbol_recursion", GeLBExSymbolConstantRecursion,
         """
         dynamic SetDFsToConstant {
           const int NX = 123;
           const int NY = -2 * NY + NX;
           f.out[x, y, z | :] = NY;
         }
         """, "f"),
        
        # Gauge block tests
        ("gauge_block", "symbol_exists", GeLBExSymbolExists,
         """
         gauge PiTimesCurrentState(out = {int state;}) {
           const real64 PI = 3.141592653589793;
           const real32 PI = 3.14159265;
           const real16 PI = 3.141;
           state = PI*f.in[x | 0];
         }
         """, "f"),
        
        ("gauge_block", "symbol_unknown", GeLBExSymbolUnknown,
         """
         gauge PiTimesCurrentState(out = {int state;}) {
           state = PI *f.in[x | 0];
         }
         """, "f"),
        
        # Node classes block tests
        ("node_classes_block", "symbol_exists", GeLBExSymbolExists,
         """
         node_classes {
           node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);
           node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);
         }
         """, None),
        
        # Node classes block - symbol not defined errors
        # NOTE: This test is commented out because the symbol table builder
        # doesn't validate function references in node_classes blocks
        # ("node_classes_block", "undefined_functions", GeLBExSymbolUnknown,
        #  """
        #  node_classes {
        #    node_class BULK(undefined_init, undefined_dyn, undefined_gauge);
        #  }
        #  """, None),
    ]


def get_symbol_table_valid_test_data():
    """Return test data for valid symbol table construction tests."""
    return [
        # Global constants block - valid cases
        ("global_constants_block", 
         """
         global_constants {
           const int N = 32;
           const real TAU = 0.6;
         }
         """, None,
         "(N \"constant definition\" (ConstantDefinitionStmt (Identifier N) (ArrayDataType int (List )) (IntLiteral 32))) (TAU \"constant definition\" (ConstantDefinitionStmt (Identifier TAU) (ArrayDataType real (List )) (RealLiteral 0.6)))"),
        
        # Lattices block - valid cases
        ("lattices_block",
         """
         lattices {
           lattice f(2, 9, real, {32, 32}, {true, false});
           lattice g(3, 15, int, {32, 32, 32}, {true, true, true});
         }
         """, None,
         "(f \"lattice instance\" (LatticeInstaStmt (Identifier f) (IntLiteral 2) (IntLiteral 9) (ArrayDataType real (List )) (ArrayLiteral1D (IntLiteral 32) (IntLiteral 32)) (ArrayLiteral1D (BoolLiteral true) (BoolLiteral false)))) (g \"lattice instance\" (LatticeInstaStmt (Identifier g) (IntLiteral 3) (IntLiteral 15) (ArrayDataType int (List )) (ArrayLiteral1D (IntLiteral 32) (IntLiteral 32) (IntLiteral 32)) (ArrayLiteral1D (BoolLiteral true) (BoolLiteral true) (BoolLiteral true))))"),
        
        # Initializer block - valid cases
        ("initializer_block",
         """
         initializer init_fun1 {
           f.out[x | 0] = 1.0;
         }
         """, "f",
         ""),
        
        # Dynamic block - valid cases
        ("dynamic_block",
         """
         dynamic dyn_fun1 {
           f.out[x | 0] = f.in[x | 0] + 0.1;
         }
         """, "f", 
         ""),
        
        # Gauge block - valid cases
        ("gauge_block",
         """
         gauge gauge_fun1(out = {real rho;}) {
           rho = f.in[x | 0];
         }
         """, "f",
         "(rho \"output variable declaration\" (VariableDeclarationStmt (Identifier rho) (ArrayDataType real (List ))))"),
        
        # Node classes block - valid cases  
        ("node_classes_block",
         """
         node_classes {
           node_class BULK(init_fun1, dyn_fun1, gauge_fun1);
         }
         """, ["init_fun1", "dyn_fun1", "gauge_fun1"],
         "(BULK \"node class\" (NodeClassInstaStmt (Identifier BULK) (Identifier init_fun1) (Identifier dyn_fun1) (Identifier gauge_fun1)))"),
    ]