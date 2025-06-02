#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import (
    get_ast,
    build_symbols_tables,
    resolve_all_constants,
    resolve_ranges,
    prevent_clashes_of_symbol_refs_with_implicits,
    prevent_clashes_of_symbol_defs_with_implicits
)
from gelb.gelb_ast.ASTNodes import (
    Range_N, IntLiteral_N, Sub_N, Identifier_N
)


def test_resolve_all_elements_range_in_paint_nodes_1d():
    """Test that : in 1D paint_nodes becomes 0:(Nx-1)"""
    # Arrange - need complete program for symbol tables
    test_string = """
    simulation_description("Test 1D range");
    
    lattices {
        lattice f(1, 1, int);
    }
    
    initializer Init {
        f.out[x | 0] = 0;
    }
    
    dynamic Update {
        f.out[x | 0] = 1;
    }
    
    gauge Output(out = {int value;}) {
        value = f.in[x | 0];
    }
    
    node_classes {
        node_class BULK(Init, Update, Output);
    }
    
    geometry {
        set_grid_size(32);
        set_grid_periodicity(false);
        nodes[:] = BULK;
    }
    """
    # Act
    ast = get_ast("gelb_program", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    ast = build_symbols_tables(ast)
    prevent_clashes_of_symbol_defs_with_implicits(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    
    # Extract the range from paint_nodes_stmt
    paint_nodes_stmt = ast.geometry.stmts[0]
    range_node = paint_nodes_stmt.lhs.elements[0]
    
    # Assert
    assert isinstance(range_node, Range_N)
    assert isinstance(range_node.low, IntLiteral_N)
    assert range_node.low.value == 0
    assert isinstance(range_node.high, Sub_N)
    assert isinstance(range_node.high.left, Identifier_N)
    assert range_node.high.left.name == 'Nx'
    assert isinstance(range_node.high.right, IntLiteral_N)
    assert range_node.high.right.value == 1


def test_resolve_all_elements_range_in_paint_nodes_2d():
    """Test that :,: in 2D paint_nodes becomes 0:(Nx-1), 0:(Ny-1)"""
    # Arrange
    test_string = """
    simulation_description("Test 2D range");
    
    lattices {
        lattice f(2, 9, real);
    }
    
    initializer Init {
        f.out[x, y | :] = 0;
    }
    
    dynamic Update {
        f.out[x, y | :] = 1;
    }
    
    gauge Output(out = {real value;}) {
        value = f.in[x, y | 0];
    }
    
    node_classes {
        node_class BULK(Init, Update, Output);
    }
    
    geometry {
        set_grid_size({128, 64});
        set_grid_periodicity({true, true});
        nodes[:,:] = BULK;
    }
    """
    # Act
    ast = get_ast("gelb_program", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    ast = build_symbols_tables(ast)
    prevent_clashes_of_symbol_defs_with_implicits(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    
    # Extract the ranges from paint_nodes_stmt
    paint_nodes_stmt = ast.geometry.stmts[0]
    range_x = paint_nodes_stmt.lhs.elements[0]
    range_y = paint_nodes_stmt.lhs.elements[1]
    
    # Assert X dimension
    assert isinstance(range_x, Range_N)
    assert isinstance(range_x.low, IntLiteral_N)
    assert range_x.low.value == 0
    assert isinstance(range_x.high, Sub_N)
    assert range_x.high.left.name == 'Nx'
    
    # Assert Y dimension
    assert isinstance(range_y, Range_N)
    assert isinstance(range_y.low, IntLiteral_N)
    assert range_y.low.value == 0
    assert isinstance(range_y.high, Sub_N)
    assert range_y.high.left.name == 'Ny'


def test_resolve_low_bound_range():
    """Test that 5: becomes 5:(Nx-1)"""
    # Arrange
    test_string = """
    simulation_description("Test low bound range");
    
    lattices {
        lattice f(1, 1, int);
    }
    
    initializer Init {
        f.out[x | 0] = 0;
    }
    
    dynamic Update {
        f.out[x | 0] = 1;
    }
    
    gauge Output(out = {int value;}) {
        value = f.in[x | 0];
    }
    
    node_classes {
        node_class BULK(Init, Update, Output);
        node_class BOUNDARY(Init, Update, Output);
    }
    
    geometry {
        set_grid_size(100);
        set_grid_periodicity(false);
        nodes[5:] = BOUNDARY;
        nodes[:5] = BULK;
    }
    """
    # Act
    ast = get_ast("gelb_program", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    ast = build_symbols_tables(ast)
    prevent_clashes_of_symbol_defs_with_implicits(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    
    # Extract the range (first paint_nodes statement)
    paint_nodes_stmt = ast.geometry.stmts[0]
    range_node = paint_nodes_stmt.lhs.elements[0]
    
    # Assert
    assert isinstance(range_node, Range_N)
    assert isinstance(range_node.low, IntLiteral_N)
    assert range_node.low.value == 5
    assert isinstance(range_node.high, Sub_N)
    assert range_node.high.left.name == 'Nx'


def test_resolve_high_bound_range():
    """Test that :10 becomes 0:10"""
    # Arrange
    test_string = """
    simulation_description("Test high bound range");
    
    lattices {
        lattice f(1, 1, int);
    }
    
    initializer Init {
        f.out[x | 0] = 0;
    }
    
    dynamic Update {
        f.out[x | 0] = 1;
    }
    
    gauge Output(out = {int value;}) {
        value = f.in[x | 0];
    }
    
    node_classes {
        node_class BULK(Init, Update, Output);
        node_class BOUNDARY(Init, Update, Output);
    }
    
    geometry {
        set_grid_size(100);
        set_grid_periodicity(false);
        nodes[:10] = BOUNDARY;
        nodes[10:] = BULK;
    }
    """
    # Act
    ast = get_ast("gelb_program", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    ast = build_symbols_tables(ast)
    prevent_clashes_of_symbol_defs_with_implicits(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    
    # Extract the range (first paint_nodes statement)
    paint_nodes_stmt = ast.geometry.stmts[0]
    range_node = paint_nodes_stmt.lhs.elements[0]
    
    # Assert
    assert isinstance(range_node, Range_N)
    assert isinstance(range_node.low, IntLiteral_N)
    assert range_node.low.value == 0
    assert isinstance(range_node.high, IntLiteral_N)
    assert range_node.high.value == 10


def test_resolve_range_in_lattice_out_selection():
    """Test range resolution in lattice output selection f.out[x,y|:]"""
    # Arrange
    test_string = """
    simulation_description("Test lattice out range");
    
    lattices {
        lattice f(2, 9, real);
    }
    
    initializer InitTest {
        f.out[x, y | :] = 0;
    }
    
    dynamic Update {
        f.out[x, y | :] = 1;
    }
    
    gauge Output(out = {real value;}) {
        value = f.in[x, y | 0];
    }
    
    node_classes {
        node_class BULK(InitTest, Update, Output);
    }
    
    geometry {
        set_grid_size({100, 100});
        set_grid_periodicity({true, true});
        nodes[:,:] = BULK;
    }
    """
    # Act
    ast = get_ast("gelb_program", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    ast = build_symbols_tables(ast)
    prevent_clashes_of_symbol_defs_with_implicits(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    
    # Extract the DFs range (last element in element_ranges)
    lattice_out_stmt = ast.initializers[0].stmts[0]
    dfs_range = lattice_out_stmt.lhs.element_ranges[-1]
    
    # Assert - DFs range should use 'q'
    assert isinstance(dfs_range, Range_N)
    assert isinstance(dfs_range.low, IntLiteral_N)
    assert dfs_range.low.value == 0
    assert isinstance(dfs_range.high, Sub_N)
    assert isinstance(dfs_range.high.left, Identifier_N)
    assert dfs_range.high.left.name == 'q'


def test_resolve_range_in_lattice_in_selection():
    """Test range resolution in lattice input selection f.in[x,y|:]"""
    # Arrange
    test_string = """
    simulation_description("Test lattice in range");
    
    lattices {
        lattice f(2, 9, real);
    }
    
    initializer Init {
        f.out[x, y | :] = 0;
    }
    
    dynamic UpdateTest {
        f.out[x, y | :] = f.in[x, y | :];
    }
    
    gauge Output(out = {real value;}) {
        value = f.in[x, y | 0];
    }
    
    node_classes {
        node_class BULK(Init, UpdateTest, Output);
    }
    
    geometry {
        set_grid_size({100, 100});
        set_grid_periodicity({true, true});
        nodes[:,:] = BULK;
    }
    """
    # Act
    ast = get_ast("gelb_program", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    ast = build_symbols_tables(ast)
    prevent_clashes_of_symbol_defs_with_implicits(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    
    # Extract the DFs range from f.in
    lattice_out_stmt = ast.dynamics[0].stmts[0]
    # The RHS contains the f.in expression
    lattice_in = lattice_out_stmt.rhs
    dfs_range = lattice_in.element_ranges[-1]
    
    # Assert
    assert isinstance(dfs_range, Range_N)
    assert isinstance(dfs_range.low, IntLiteral_N)
    assert dfs_range.low.value == 0
    assert isinstance(dfs_range.high, Sub_N)
    assert dfs_range.high.left.name == 'q'


def test_no_modification_of_explicit_ranges():
    """Test that explicit ranges like 3:7 are not modified"""
    # Arrange
    test_string = """
    simulation_description("Test explicit range");
    
    lattices {
        lattice f(1, 1, int);
    }
    
    initializer Init {
        f.out[x | 0] = 0;
    }
    
    dynamic Update {
        f.out[x | 0] = 1;
    }
    
    gauge Output(out = {int value;}) {
        value = f.in[x | 0];
    }
    
    node_classes {
        node_class BULK(Init, Update, Output);
    }
    
    geometry {
        set_grid_size(100);
        set_grid_periodicity(false);
        nodes[3:7] = BULK;
    }
    """
    # Act
    ast = get_ast("gelb_program", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    ast = build_symbols_tables(ast)
    prevent_clashes_of_symbol_defs_with_implicits(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    
    # Extract the range
    paint_nodes_stmt = ast.geometry.stmts[0]
    range_node = paint_nodes_stmt.lhs.elements[0]
    
    # Assert - should remain unchanged
    assert isinstance(range_node, Range_N)
    assert isinstance(range_node.low, IntLiteral_N)
    assert range_node.low.value == 3
    assert isinstance(range_node.high, IntLiteral_N)
    assert range_node.high.value == 7


def test_complete_program_with_ranges():
    """Test range resolution in a complete program"""
    # Arrange
    test_string = """
    simulation_description("Test program with ranges");
    
    lattices {
        lattice f(1, 3, real);
    }
    
    initializer Init {
        f.out[x | :] = 0;
    }
    
    dynamic Update {
        f.out[x | :] = f.in[x | :] + 1;
    }
    
    gauge Output(out = {real value;}) {
        value = f.in[x | 0];
    }
    
    node_classes {
        node_class BULK(Init, Update, Output);
    }
    
    geometry {
        set_grid_size(100);
        set_grid_periodicity(false);
        nodes[:] = BULK;
    }
    """
    # Act
    ast = get_ast("gelb_program", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    ast = build_symbols_tables(ast)
    prevent_clashes_of_symbol_defs_with_implicits(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    
    # Check geometry range
    geometry_paint_nodes = ast.geometry.stmts[0]
    geometry_range = geometry_paint_nodes.lhs.elements[0]
    assert isinstance(geometry_range.low, IntLiteral_N)
    assert geometry_range.low.value == 0
    assert isinstance(geometry_range.high, Sub_N)
    assert geometry_range.high.left.name == 'Nx'
    
    # Check initializer DFs range
    init_stmt = ast.initializers[0].stmts[0]
    init_dfs_range = init_stmt.lhs.element_ranges[-1]
    assert isinstance(init_dfs_range.low, IntLiteral_N)
    assert init_dfs_range.low.value == 0
    assert isinstance(init_dfs_range.high, Sub_N)
    assert init_dfs_range.high.left.name == 'q'


def test_ast_unchanged_str():
    """Test that AST string representation shows the resolved ranges"""
    # Arrange
    test_string = """
    simulation_description("Test AST string");
    
    lattices {
        lattice f(1, 1, int);
    }
    
    initializer Init {
        f.out[x | 0] = 0;
    }
    
    dynamic Update {
        f.out[x | 0] = 1;
    }
    
    gauge Output(out = {int value;}) {
        value = f.in[x | 0];
    }
    
    node_classes {
        node_class BULK(Init, Update, Output);
    }
    
    geometry {
        set_grid_size(32);
        set_grid_periodicity(false);
        nodes[:] = BULK;
    }
    """
    # Act
    ast = get_ast("gelb_program", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    ast = build_symbols_tables(ast)
    prevent_clashes_of_symbol_defs_with_implicits(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    
    # Check that the AST string shows resolved ranges
    ast_str = str(ast)
    # The paint_nodes statement should show (Range (IntLiteral 0) (Sub (Identifier Nx) (IntLiteral 1)))
    assert "(Range (IntLiteral 0) (Sub (Identifier Nx) (IntLiteral 1)))" in ast_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])