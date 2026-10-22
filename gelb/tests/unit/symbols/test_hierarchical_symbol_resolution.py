#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import get_ast, build_symbols_tables
from gelb.utils.exceptions import (
    GeLBExSymbolExists, GeLBExSymbolUnknown, GeLBExSymbolConstantRecursion
)
from gelb.frontend.SymbolsTable import SymbolsTable
from gelb.gelb_ast.SymbolDefinition import SymbolDefinition
from gelb.gelb_ast.ASTNodes import IntLiteral_N
from gelb.utils.CodeRange import CodeRange


def test_symbols_table_parent_lookup():
    """
    Test the core SymbolsTable parent lookup functionality.
    """
    # Arrange - create a parent table with global constants
    parent_table = SymbolsTable()
    global_symbol = SymbolDefinition(
        "GLOBAL_VAR",
        "constant definition",
        IntLiteral_N(CodeRange(1, 15, 1, 17), 42)
    )
    parent_table.append(global_symbol)
    
    # Create a child table with a local symbol
    child_table = SymbolsTable(parent_table)
    local_symbol = SymbolDefinition(
        "LOCAL_VAR",
        "constant definition", 
        IntLiteral_N(CodeRange(2, 15, 2, 17), 24)
    )
    child_table.append(local_symbol)
    
    # Assert - test hierarchical lookup
    assert child_table.contains("LOCAL_VAR")  # local symbol
    assert child_table.contains("GLOBAL_VAR")  # parent symbol
    assert not child_table.contains("UNKNOWN_VAR")  # unknown symbol
    
    # Test that local lookup only finds local symbols
    assert child_table.contains_local("LOCAL_VAR")
    assert not child_table.contains_local("GLOBAL_VAR")
    
    # Test that get_symbol_definition works hierarchically
    local_def = child_table.get_symbol_definition("LOCAL_VAR")
    assert local_def is not None
    assert str(local_def.name) == "LOCAL_VAR"
    
    global_def = child_table.get_symbol_definition("GLOBAL_VAR")
    assert global_def is not None
    assert str(global_def.name) == "GLOBAL_VAR"
    
    unknown_def = child_table.get_symbol_definition("UNKNOWN_VAR")
    assert unknown_def is None


def test_symbols_table_local_precedence():
    """
    Test that local symbols take precedence over parent symbols.
    """
    # Arrange - parent and child both have symbol with same name
    parent_table = SymbolsTable()
    parent_symbol = SymbolDefinition(
        "SHARED_NAME",
        "constant definition",
        IntLiteral_N(CodeRange(1, 15, 1, 17), 100)
    )
    parent_table.append(parent_symbol)
    
    child_table = SymbolsTable(parent_table)
    child_symbol = SymbolDefinition(
        "SHARED_NAME",
        "constant definition",
        IntLiteral_N(CodeRange(2, 15, 2, 17), 200)
    )
    child_table.append(child_symbol)
    
    # Assert - local symbol should take precedence
    found_symbol = child_table.get_symbol_definition("SHARED_NAME")
    assert found_symbol is not None
    assert found_symbol.value.value == 200  # local value, not parent value


def test_symbols_table_duplicate_prevention():
    """
    Test that duplicate symbols in the same scope are prevented.
    """
    # Arrange
    parent_table = SymbolsTable()
    parent_symbol = SymbolDefinition(
        "PARENT_VAR",
        "constant definition",
        IntLiteral_N(CodeRange(1, 15, 1, 17), 42)
    )
    parent_table.append(parent_symbol)
    
    child_table = SymbolsTable(parent_table)
    first_symbol = SymbolDefinition(
        "LOCAL_VAR",
        "constant definition",
        IntLiteral_N(CodeRange(2, 15, 2, 17), 24)
    )
    child_table.append(first_symbol)
    
    # Attempt to add duplicate local symbol
    duplicate_symbol = SymbolDefinition(
        "LOCAL_VAR",  # Same name as first_symbol
        "constant definition",
        IntLiteral_N(CodeRange(3, 15, 3, 17), 99)
    )
    
    # Assert - should raise GeLBExSymbolExists for local duplicate
    with pytest.raises(GeLBExSymbolExists):
        child_table.append(duplicate_symbol)
    
    # But adding a symbol with same name as parent should be allowed (shadowing)
    shadowing_symbol = SymbolDefinition(
        "PARENT_VAR",  # Same name as parent symbol
        "constant definition",
        IntLiteral_N(CodeRange(4, 15, 4, 17), 999)
    )
    child_table.append(shadowing_symbol)  # This should succeed


def test_lattices_with_global_constants_integration():
    """
    Test that lattices can access global constants in a simple program.
    """
    test_string = """simulation_description("Test lattices accessing global constants");

global_constants {
  const int D = 2;
  const int Q = 9;
}

lattices {
  lattice f(D, Q, real64, {32, 32}, {true, true});
}

initializer Init {
  f.out[x,y | :] = 0.0;
}

dynamic Update {
  f.out[x,y | :] = f.in[x,y | :];
}

gauge Output -> (real val) {
  val = f.in[x,y | 0];
}

node_classes {
  node_class BULK(Init, Update, Output);
}

geometry {
  nodes[:,:] = BULK;
}"""
    # Act
    ast = get_ast("gelb_program", test_string)
    ast = build_symbols_tables(ast)
    
    # Assert - lattices should be able to find global constants
    assert ast.lattices.symbol_defs.contains("D")   # from global constants
    assert ast.lattices.symbol_defs.contains("Q")   # from global constants  
    assert ast.lattices.symbol_defs.contains("f")   # local lattice
    
    # Verify that D and Q come from parent, not local
    assert not ast.lattices.symbol_defs.contains_local("D")
    assert not ast.lattices.symbol_defs.contains_local("Q")
    assert ast.lattices.symbol_defs.contains_local("f")  # Lattice is local


def test_unknown_symbol_error_with_hierarchical_lookup():
    """
    Test that unknown symbols still raise errors even with hierarchical lookup.
    """
    test_string = """simulation_description("Test unknown symbol error");

global_constants {
  const int KNOWN_VAR = 42;
}

lattices {
  lattice f(2, UNKNOWN_VAR, real64, {32, 32}, {true, true});  // UNKNOWN_VAR not defined anywhere
}

initializer Init {
  f.out[x,y | :] = 0.0;
}

dynamic Update {
  f.out[x,y | :] = f.in[x,y | :];
}

gauge Output -> (real val) {
  val = f.in[x,y | 0];
}

node_classes {
  node_class BULK(Init, Update, Output);
}

geometry {
  nodes[:,:] = BULK;
}"""
    # Act & Assert - should raise GeLBExSymbolUnknown for truly unknown symbols
    ast = get_ast("gelb_program", test_string)
    with pytest.raises(GeLBExSymbolUnknown):
        ast = build_symbols_tables(ast)


def test_real_world_integration_ex31_style():
    """
    Test using the structure of ex31_simple_constants_test.gelb
    """
    # This uses a complete program structure - exact copy from ex31
    test_string = """simulation_description("Simple test for global constants resolution");

global_constants {
  const int SIZE = 16;
  const int DFS = 3;
}

lattices {
  lattice f(1, DFS, int, SIZE, false);  // DFS should resolve to 3, SIZE to 16
}

initializer Init {
  f.out[x | :] = 0;
}

dynamic Update {
  f.out[x | :] = f.in[x | :] + 1;
}

gauge Output -> (int val) {
  val = f.in[x | 0];
}

node_classes {
  node_class BULK(Init, Update, Output);
}

geometry {
  nodes[:] = BULK;
}"""
    # Act
    ast = get_ast("gelb_program", test_string)
    ast = build_symbols_tables(ast)
    
    # Assert - verify hierarchical symbol resolution worked
    # Global constants should be defined
    assert ast.global_constants.symbol_defs.contains("SIZE")
    assert ast.global_constants.symbol_defs.contains("DFS")
    
    # Lattices should be able to access DFS and SIZE from global constants
    assert ast.lattices.symbol_defs.contains("DFS")  # via parent lookup
    assert ast.lattices.symbol_defs.contains("SIZE") # via parent lookup  
    assert ast.lattices.symbol_defs.contains("f")    # local lattice
    
    # Check if geometry has symbol_defs (it might not always have one)
    if ast.geometry.symbol_defs is not None:
        # Geometry should be able to access SIZE from global constants
        assert ast.geometry.symbol_defs.contains("SIZE")  # via parent lookup
        assert ast.geometry.symbol_defs.contains("BULK")  # from node classes
        
        # Verify the parent table structure
        # Geometry should have program's symbol table as parent (to access global constants and node classes)
        # Program.symbol_defs is the root table containing global constants
        assert ast.geometry.symbol_defs.parent_table is ast.symbol_defs
        assert ast.symbol_defs.parent_table is None  # Program.symbol_defs is the root
    
    # Verify the parent table structure for other blocks
    assert ast.lattices.symbol_defs.parent_table is ast.symbol_defs
    assert ast.node_classes.symbol_defs.parent_table is ast.symbol_defs


def test_minimal_global_constants_with_hierarchical_lookup():
    """
    Test that hierarchical symbol resolution works with minimal global constants.
    """
    test_string = """simulation_description("Test minimal global constants");

global_constants {
  const int Q_VALUE = 9;
}

lattices {
  lattice f(1, Q_VALUE, int, 16, false);  // Using global constant
}

initializer Init {
  f.out[x | :] = 0;
}

dynamic Update {
  f.out[x | :] = f.in[x | :] + 1;
}

gauge Output -> (int val) {
  val = f.in[x | 0];
}

node_classes {
  node_class BULK(Init, Update, Output);
}

geometry {
  nodes[:] = BULK;
}"""
    # Act
    ast = get_ast("gelb_program", test_string)
    ast = build_symbols_tables(ast)
    
    # Assert - should work fine with hierarchical lookup
    assert ast.global_constants.symbol_defs.contains("Q_VALUE")  # Global constant exists
    assert ast.lattices.symbol_defs.contains("f")       # Local lattice
    assert ast.lattices.symbol_defs.contains("Q_VALUE") # Can access global constant
    
    # Parent table structure should be set up
    assert ast.lattices.symbol_defs.parent_table is ast.symbol_defs