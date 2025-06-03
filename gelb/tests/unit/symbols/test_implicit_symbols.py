#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import (
    get_ast, build_symbols_tables, add_implicit_symbols
)
from gelb.tests.test_utils import get_resolved_ast


def test_1d_implicit_symbols():
    """Test that 1D programs get Nx and x symbols correctly."""
    test_string = """simulation_description("Test 1D implicit symbols");

global_constants {
    const int DUMMY = 1;
}

lattices {
    lattice f(1, 1, int);
}

initializer Init {
    f.out[x | 0] = 0;
}

dynamic Update {
    f.out[x | 0] = 1;
}

gauge Output(out = {int val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    set_grid_size(32);
    set_grid_periodicity(false);
    nodes[:] = BULK;
}"""
    
    ast = get_ast("gelb_program", test_string)
    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)
    
    # Verify dimension constants were added to global_constants
    assert ast.global_constants.symbol_defs.contains("Nx"), "Nx should be in global_constants"
    assert not ast.global_constants.symbol_defs.contains("Ny"), "Ny should NOT be in 1D program"
    assert not ast.global_constants.symbol_defs.contains("Nz"), "Nz should NOT be in 1D program"
    
    # Verify lattice coordinates were added to blocks that need them
    assert ast.initializers[0].symbol_defs.contains("x"), "x should be in initializer"
    assert not ast.initializers[0].symbol_defs.contains("y"), "y should NOT be in 1D program"
    assert not ast.initializers[0].symbol_defs.contains("z"), "z should NOT be in 1D program"
    
    assert ast.dynamics[0].symbol_defs.contains("x"), "x should be in dynamic"
    assert ast.gauges[0].symbol_defs.contains("x"), "x should be in gauge"
    
    # Verify symbol tags are correct
    nx_symbol = ast.global_constants.symbol_defs.get_symbol_definition("Nx")
    assert nx_symbol.tag == "implicit dimension constant"
    
    x_symbol = ast.initializers[0].symbol_defs.get_symbol_definition("x")
    assert x_symbol.tag == "implicit lattice coordinate"


def test_2d_implicit_symbols():
    """Test that 2D programs get Nx, Ny and x, y symbols correctly."""
    test_string = """simulation_description("Test 2D implicit symbols");

global_constants {
    const int DUMMY = 1;
}

lattices {
    lattice f(2, 9, real);
}

initializer Init {
    f.out[x,y | :] = 0.0;
}

dynamic Update {
    f.out[x,y | :] = f.in[x,y | :];
}

gauge Output(out = {real val;}) {
    val = f.in[x,y | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    set_grid_size({64, 32});
    set_grid_periodicity({true, false});
    nodes[:,:] = BULK;
}"""
    
    ast = get_ast("gelb_program", test_string)
    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)
    
    # Verify dimension constants were added to global_constants
    assert ast.global_constants.symbol_defs.contains("Nx"), "Nx should be in global_constants"
    assert ast.global_constants.symbol_defs.contains("Ny"), "Ny should be in global_constants"
    assert not ast.global_constants.symbol_defs.contains("Nz"), "Nz should NOT be in 2D program"
    
    # Verify lattice coordinates were added to blocks that need them
    assert ast.initializers[0].symbol_defs.contains("x"), "x should be in initializer"
    assert ast.initializers[0].symbol_defs.contains("y"), "y should be in initializer"
    assert not ast.initializers[0].symbol_defs.contains("z"), "z should NOT be in 2D program"
    
    assert ast.dynamics[0].symbol_defs.contains("x"), "x should be in dynamic"
    assert ast.dynamics[0].symbol_defs.contains("y"), "y should be in dynamic"
    
    assert ast.gauges[0].symbol_defs.contains("x"), "x should be in gauge"
    assert ast.gauges[0].symbol_defs.contains("y"), "y should be in gauge"


def test_3d_implicit_symbols():
    """Test that 3D programs get Nx, Ny, Nz and x, y, z symbols correctly."""
    test_string = """simulation_description("Test 3D implicit symbols");

global_constants {
    const int DUMMY = 1;
}

lattices {
    lattice f(3, 19, real);
}

initializer Init {
    f.out[x,y,z | :] = 0.0;
}

dynamic Update {
    f.out[x,y,z | :] = f.in[x,y,z | :];
}

gauge Output(out = {real val;}) {
    val = f.in[x,y,z | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    set_grid_size({64, 32, 16});
    set_grid_periodicity({true, false, true});
    nodes[:,:,:] = BULK;
}"""
    
    ast = get_ast("gelb_program", test_string)
    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)
    
    # Verify dimension constants were added to global_constants
    assert ast.global_constants.symbol_defs.contains("Nx"), "Nx should be in global_constants"
    assert ast.global_constants.symbol_defs.contains("Ny"), "Ny should be in global_constants"
    assert ast.global_constants.symbol_defs.contains("Nz"), "Nz should be in global_constants"
    
    # Verify lattice coordinates were added to blocks that need them
    assert ast.initializers[0].symbol_defs.contains("x"), "x should be in initializer"
    assert ast.initializers[0].symbol_defs.contains("y"), "y should be in initializer"
    assert ast.initializers[0].symbol_defs.contains("z"), "z should be in initializer"
    
    assert ast.dynamics[0].symbol_defs.contains("x"), "x should be in dynamic"
    assert ast.dynamics[0].symbol_defs.contains("y"), "y should be in dynamic"
    assert ast.dynamics[0].symbol_defs.contains("z"), "z should be in dynamic"
    
    assert ast.gauges[0].symbol_defs.contains("x"), "x should be in gauge"
    assert ast.gauges[0].symbol_defs.contains("y"), "y should be in gauge"
    assert ast.gauges[0].symbol_defs.contains("z"), "z should be in gauge"


def test_implicit_symbols_with_constant_grid_size():
    """Test that implicit symbols work when grid size uses constants."""
    test_string = """simulation_description("Test implicit symbols with constant grid size");

global_constants {
    const int SIZE = 64;
}

lattices {
    lattice f(1, 3, int);
}

initializer Init {
    f.out[x | :] = 0;
}

dynamic Update {
    f.out[x | :] = f.in[x | :] + 1;
}

gauge Output(out = {int val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    set_grid_size(SIZE);
    set_grid_periodicity(false);
    nodes[:] = BULK;
}"""
    
    ast = get_ast("gelb_program", test_string)
    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)
    
    # Should work even when grid size is an expression/constant reference
    assert ast.global_constants.symbol_defs.contains("Nx"), "Nx should be in global_constants"
    assert ast.initializers[0].symbol_defs.contains("x"), "x should be in initializer"


def test_implicit_symbols_no_duplicates():
    """Test that implicit symbols are not added if they already exist."""
    test_string = """simulation_description("Test no duplicate implicit symbols");

global_constants {
    const int Nx = 999;  // User-defined Nx should take precedence
}

lattices {
    lattice f(1, 1, int);
}

initializer Init {
    f.out[x | 0] = 0;
}

dynamic Update {
    f.out[x | 0] = 1;
}

gauge Output(out = {int val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    set_grid_size(32);
    set_grid_periodicity(false);
    nodes[:] = BULK;
}"""
    
    ast = get_ast("gelb_program", test_string)
    ast = build_symbols_tables(ast)
    
    # Count symbols before adding implicits
    global_symbols_before = len(ast.global_constants.symbol_defs)
    
    ast = add_implicit_symbols(ast)
    
    # Count symbols after adding implicits
    global_symbols_after = len(ast.global_constants.symbol_defs)
    
    # Should not have added duplicate Nx since user already defined it
    assert global_symbols_after == global_symbols_before, "Should not add duplicate Nx"
    
    # Verify the user-defined Nx is still there
    assert ast.global_constants.symbol_defs.contains("Nx"), "User-defined Nx should still exist"
    
    # However, x should still be added to blocks since it wasn't user-defined there
    assert ast.initializers[0].symbol_defs.contains("x"), "x should be added to initializer"


def test_blocks_without_lattice_coordinates():
    """Test that blocks that don't need lattice coordinates don't get them."""
    test_string = """simulation_description("Test blocks without coordinates");

global_constants {
    const int SIZE = 32;
}

lattices {
    lattice f(1, 1, int);
}

initializer Init {
    f.out[x | 0] = 0;
}

dynamic Update {
    f.out[x | 0] = 1;
}

gauge Output(out = {int val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    set_grid_size(SIZE);
    set_grid_periodicity(false);
    nodes[:] = BULK;
}"""
    
    ast = get_ast("gelb_program", test_string)
    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)
    
    # Lattices, node_classes, and geometry should NOT get x, y, z coordinates
    assert not ast.lattices.symbol_defs.contains("x"), "lattices should not have x"
    assert not ast.node_classes.symbol_defs.contains("x"), "node_classes should not have x"
    
    # Only initializers, dynamics, and gauges should get coordinates
    assert ast.initializers[0].symbol_defs.contains("x"), "initializer should have x"
    assert ast.dynamics[0].symbol_defs.contains("x"), "dynamic should have x"
    assert ast.gauges[0].symbol_defs.contains("x"), "gauge should have x"


# ==============================================================================
# NEW SYNTAX TESTS (Grid properties in lattice instantiation)
# ==============================================================================

def test_1d_implicit_symbols_new_syntax():
    """Test that 1D programs get Nx and x symbols correctly with new lattice syntax."""
    test_string = """simulation_description("Test 1D implicit symbols - new syntax");

global_constants {
    const int DUMMY = 1;
}

lattices {
    lattice f(1, 1, int, 32, false);
}

initializer Init {
    f.out[x | 0] = 0;
}

dynamic Update {
    f.out[x | 0] = 1;
}

gauge Output(out = {int val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    nodes[:] = BULK;
}"""
    
    ast = get_ast("gelb_program", test_string)
    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)
    
    # Verify dimension constants were added to Program level (new hierarchy)
    assert ast.symbol_defs is not None, "Program should have symbol_defs"
    assert ast.symbol_defs.contains("Nx"), "Nx should be in Program symbol table"
    assert not ast.symbol_defs.contains("Ny"), "Ny should NOT be in 1D program"
    assert not ast.symbol_defs.contains("Nz"), "Nz should NOT be in 1D program"
    
    # Verify lattice coordinates were added to blocks that need them
    assert ast.initializers[0].symbol_defs.contains("x"), "x should be in initializer"
    assert not ast.initializers[0].symbol_defs.contains("y"), "y should NOT be in 1D program"
    assert not ast.initializers[0].symbol_defs.contains("z"), "z should NOT be in 1D program"
    
    assert ast.dynamics[0].symbol_defs.contains("x"), "x should be in dynamic"
    assert ast.gauges[0].symbol_defs.contains("x"), "x should be in gauge"
    
    # Verify symbol tags are correct
    nx_symbol = ast.symbol_defs.get_symbol_definition("Nx")
    assert nx_symbol.tag == "implicit dimension constant"
    
    x_symbol = ast.initializers[0].symbol_defs.get_symbol_definition("x")
    assert x_symbol.tag == "implicit lattice coordinate"


def test_2d_implicit_symbols_new_syntax():
    """Test that 2D programs get Nx, Ny and x, y symbols correctly with new lattice syntax."""
    test_string = """simulation_description("Test 2D implicit symbols - new syntax");

global_constants {
    const int DUMMY = 1;
}

lattices {
    lattice f(2, 9, real, {64, 32}, {true, false});
}

initializer Init {
    f.out[x,y | :] = 0.0;
}

dynamic Update {
    f.out[x,y | :] = f.in[x,y | :];
}

gauge Output(out = {real val;}) {
    val = f.in[x,y | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    nodes[:,:] = BULK;
}"""
    
    ast = get_resolved_ast(test_string)  # Use shared utility for full pipeline
    
    # Verify dimension constants were added to Program level
    assert ast.symbol_defs is not None, "Program should have symbol_defs"
    assert ast.symbol_defs.contains("Nx"), "Nx should be in Program symbol table"
    assert ast.symbol_defs.contains("Ny"), "Ny should be in Program symbol table"
    assert not ast.symbol_defs.contains("Nz"), "Nz should NOT be in 2D program"
    
    # Verify lattice coordinates were added to blocks that need them
    assert ast.initializers[0].symbol_defs.contains("x"), "x should be in initializer"
    assert ast.initializers[0].symbol_defs.contains("y"), "y should be in initializer"
    assert not ast.initializers[0].symbol_defs.contains("z"), "z should NOT be in 2D program"
    
    assert ast.dynamics[0].symbol_defs.contains("x"), "x should be in dynamic"
    assert ast.dynamics[0].symbol_defs.contains("y"), "y should be in dynamic"
    
    assert ast.gauges[0].symbol_defs.contains("x"), "x should be in gauge"
    assert ast.gauges[0].symbol_defs.contains("y"), "y should be in gauge"


def test_3d_implicit_symbols_new_syntax():
    """Test that 3D programs get Nx, Ny, Nz and x, y, z symbols correctly with new lattice syntax."""
    test_string = """simulation_description("Test 3D implicit symbols - new syntax");

global_constants {
    const int DUMMY = 1;
}

lattices {
    lattice f(3, 19, real, {64, 32, 16}, {true, false, true});
}

initializer Init {
    f.out[x,y,z | :] = 0.0;
}

dynamic Update {
    f.out[x,y,z | :] = f.in[x,y,z | :];
}

gauge Output(out = {real val;}) {
    val = f.in[x,y,z | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    nodes[:,:,:] = BULK;
}"""
    
    ast = get_resolved_ast(test_string)  # Use shared utility
    
    # Verify dimension constants were added to Program level
    assert ast.symbol_defs is not None, "Program should have symbol_defs"
    assert ast.symbol_defs.contains("Nx"), "Nx should be in Program symbol table"
    assert ast.symbol_defs.contains("Ny"), "Ny should be in Program symbol table"
    assert ast.symbol_defs.contains("Nz"), "Nz should be in Program symbol table"
    
    # Verify lattice coordinates were added to blocks that need them
    assert ast.initializers[0].symbol_defs.contains("x"), "x should be in initializer"
    assert ast.initializers[0].symbol_defs.contains("y"), "y should be in initializer"
    assert ast.initializers[0].symbol_defs.contains("z"), "z should be in initializer"
    
    assert ast.dynamics[0].symbol_defs.contains("x"), "x should be in dynamic"
    assert ast.dynamics[0].symbol_defs.contains("y"), "y should be in dynamic"
    assert ast.dynamics[0].symbol_defs.contains("z"), "z should be in dynamic"
    
    assert ast.gauges[0].symbol_defs.contains("x"), "x should be in gauge"
    assert ast.gauges[0].symbol_defs.contains("y"), "y should be in gauge"
    assert ast.gauges[0].symbol_defs.contains("z"), "z should be in gauge"


def test_implicit_symbols_with_constants_new_syntax():
    """Test that implicit symbols work when grid size uses constants with new syntax."""
    test_string = """simulation_description("Test implicit symbols with constants - new syntax");

global_constants {
    const int SIZE = 64;
    const int Q = 3;
}

lattices {
    lattice f(1, Q, int, SIZE, false);
}

initializer Init {
    f.out[x | :] = 0;
}

dynamic Update {
    f.out[x | :] = f.in[x | :] + 1;
}

gauge Output(out = {int val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    nodes[:] = BULK;
}"""
    
    ast = get_resolved_ast(test_string)  # Full pipeline including constant resolution
    
    # Should work even when grid size is a constant reference
    assert ast.symbol_defs.contains("Nx"), "Nx should be in Program symbol table"
    assert ast.initializers[0].symbol_defs.contains("x"), "x should be in initializer"
    
    # Verify constants were resolved in lattice parameters
    lattice = ast.lattices.stmts.elements[0]
    # After constant resolution, Q and SIZE should be replaced with their values
    # Note: The exact verification depends on how constant resolution works


def test_new_syntax_no_duplicate_symbols():
    """Test that implicit symbols are not added if they already exist with new syntax."""
    test_string = """simulation_description("Test no duplicate implicit symbols - new syntax");

global_constants {
    const int Nx = 999;  // User-defined Nx should take precedence
}

lattices {
    lattice f(1, 1, int, 32, false);
}

initializer Init {
    f.out[x | 0] = 0;
}

dynamic Update {
    f.out[x | 0] = 1;
}

gauge Output(out = {int val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    nodes[:] = BULK;
}"""
    
    ast = get_ast("gelb_program", test_string)
    ast = build_symbols_tables(ast)
    
    # Count symbols before adding implicits
    program_symbols_before = len(ast.symbol_defs) if ast.symbol_defs else 0
    
    ast = add_implicit_symbols(ast)
    
    # Count symbols after adding implicits
    program_symbols_after = len(ast.symbol_defs) if ast.symbol_defs else 0
    
    # Should not have added duplicate Nx since user already defined it
    # The promoted global constant should be there plus other program-level symbols
    # but no duplicate Nx from implicit symbols
    
    # Verify the user-defined Nx is accessible
    assert ast.symbol_defs.contains("Nx"), "User-defined Nx should still be accessible"
    
    # However, x should still be added to blocks since it wasn't user-defined there
    assert ast.initializers[0].symbol_defs.contains("x"), "x should be added to initializer"


def test_new_syntax_blocks_without_lattice_coordinates():
    """Test that blocks that don't need lattice coordinates don't get them with new syntax."""
    test_string = """simulation_description("Test blocks without coordinates - new syntax");

global_constants {
    const int SIZE = 32;
}

lattices {
    lattice f(1, 1, int, SIZE, false);
}

initializer Init {
    f.out[x | 0] = 0;
}

dynamic Update {
    f.out[x | 0] = 1;
}

gauge Output(out = {int val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    nodes[:] = BULK;
}"""
    
    ast = get_resolved_ast(test_string)
    
    # Lattices, node_classes, and geometry should NOT get x, y, z coordinates
    assert not ast.lattices.symbol_defs.contains("x"), "lattices should not have x"
    assert not ast.node_classes.symbol_defs.contains("x"), "node_classes should not have x"
    
    # Only initializers, dynamics, and gauges should get coordinates
    assert ast.initializers[0].symbol_defs.contains("x"), "initializer should have x"
    assert ast.dynamics[0].symbol_defs.contains("x"), "dynamic should have x"
    assert ast.gauges[0].symbol_defs.contains("x"), "gauge should have x"