#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import (
    ASTBuilderVisitor,
    get_ast,
    prevent_clashes_of_symbol_refs_with_implicits
)
from gelb.utils.exceptions import (
    GeLBExSyntaxError,
    GeLBExSymbolNotAllowedHere
)


def test_global_constants_block_invalid1():
    """Invalid, because we refer to x in global_constants_block."""
    # Arrange
    test_string = """
    global_constants { //
      const int TUTU = x;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_global_constants_block_invalid2():
    """Invalid, because we refer to y in global_constants_block."""
    # Arrange
    test_string = """
    global_constants { //
      const int TUTU = y;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_global_constants_block_invalid3():
    """Invalid, because we refer to z in global_constants_block."""
    # Arrange
    test_string = """
    global_constants { //
      const int TUTU = z;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_global_constants_block_invalid4():
    """Invalid, because we refer to Nx in global_constants_block."""
    # Arrange
    test_string = """
    global_constants { //
      const int TUTU = Nx;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_global_constants_block_invalid5():
    """Invalid, because we refer to Ny in global_constants_block."""
    # Arrange
    test_string = """
    global_constants { //
      const int TUTU = Ny;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_global_constants_block_invalid6():
    """Invalid, because we refer to Nz in global_constants_block."""
    # Arrange
    test_string = """
    global_constants { //
      const int TUTU = Nz;
    }
    """
    # Act
    ast = get_ast("global_constants_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid1():
    """Invalid, because we refer to x in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(x, 1, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid2():
    """Invalid, because we refer to x in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(1, x, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid3():
    """Invalid, because we refer to y in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(y, 1, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid4():
    """Invalid, because we refer to y in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(1, y, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid5():
    """Invalid, because we refer to z in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(z, 1, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid6():
    """Invalid, because we refer to z in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(1, z, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid7():
    """Invalid, because we refer to Nx in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(Nx, 1, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid8():
    """Invalid, because we refer to Nx in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(1, Nx, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid9():
    """Invalid, because we refer to Ny in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(Ny, 1, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid10():
    """Invalid, because we refer to Ny in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(1, Ny, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid11():
    """Invalid, because we refer to Nz in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(Nz, 1, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_lattices_block_invalid12():
    """Invalid, because we refer to Nz in lattices_block."""
    # Arrange
    test_string = """
    lattices { //
      lattice f(1, Nz, int);
    }
    """
    # Act
    ast = get_ast("lattices_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_initializer_block_valid1():
    """OK to use x inside an initializer."""
    # Arrange
    test_string = """
    initializer Test { //
      f.out[x | 0] = 0;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    pass


def test_initializer_block_valid2():
    """OK to use x inside an initializer."""
    # Arrange
    test_string = """
    initializer Test { //
      f.out[x | 0] = x;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    pass


def test_initializer_block_invalid1():
    """
    Not OK to use x for initializing a constant inside an initializer.
    """
    # Arrange
    test_string = """
    initializer Test { //
      const real64 TMP = x;
      f.out[x | 0] = TMP;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_initializer_block_invalid2():
    """
    Not OK to overwrite the implicit variable x.
    """
    # Arrange
    test_string = """
    initializer Test { //
      x = 23;
      f.out[x | 0] = 0;
    }
    """
    # Act
    ast = get_ast("initializer_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_dynamic_block_valid1():
    """OK to use x inside a dynamic."""
    # Arrange
    test_string = """
    dynamic Test { //
      f.out[x | 0] = f.in[x | 0] + 1;
    }
    """
    # Act
    ast = get_ast("dynamic_block", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    pass


def test_dynamic_block_valid2():
    """OK to use x inside a dynamic."""
    # Arrange
    test_string = """
    dynamic Test { //
      f.out[x | 0] = x;
    }
    """
    # Act
    ast = get_ast("dynamic_block", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    pass


def test_dynamic_block_invalid1():
    """
    Not OK to use x for initializing a constant inside a dynamic.
    """
    # Arrange
    test_string = """
    dynamic Test { //
      const real64 TMP = x;
      f.out[x | 0] = TMP;
    }
    """
    # Act
    ast = get_ast("dynamic_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_dynamic_block_invalid2():
    """
    Not OK to overwrite the implicit variable x.
    """
    # Arrange
    test_string = """
    dynamic Test { //
      x = 23;
      f.out[x | 0] = 0;
    }
    """
    # Act
    ast = get_ast("dynamic_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_gauge_block_valid1():
    """OK to use x inside a gauge."""
    # Arrange
    test_string = """
    gauge CurrentState(out = {int state;}) { //
      state = f.in[x | 0];
    }
    """
    # Act
    ast = get_ast("gauge_block", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    pass


def test_gauge_block_invalid1():
    """
    Not OK to use x for initializing a constant inside a gauge.
    """
    # Arrange
    test_string = """
    gauge CurrentState(out = {int state;}) { //
      const real64 TMP = x;
      state = f.in[x | 0] + TMP;
    }
    """
    # Act
    ast = get_ast("gauge_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_gauge_block_invalid2():
    """
    Not OK to overwrite the implicit variable x.
    """
    # Arrange
    test_string = """
    gauge CurrentState(out = {int state;}) { //
      x = 23;
      state = f.in[x | 0] + x;
    }
    """
    # Act
    ast = get_ast("gauge_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_node_classes_block_invalid1():
    """
    Not OK to have a node-class named x.
    """
    # Arrange
    test_string = """
    node_classes { //
      node_class x(SetDFsToZero, IncrementDFs, CurrentState);
    }
    """
    # Act
    ast = get_ast("node_classes_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_node_classes_block_invalid2():
    """
    Not OK to have a node-class named Nx.
    """
    # Arrange
    test_string = """
    node_classes { //
      node_class Nx(SetDFsToZero, IncrementDFs, CurrentState);
    }
    """
    # Act
    ast = get_ast("node_classes_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_node_classes_block_invalid3():
    """
    Not OK to refer to an initializer named x.
    """
    # Arrange
    test_string = """
    node_classes { //
      node_class BULK(x, IncrementDFs, CurrentState);
    }
    """
    # Act
    ast = get_ast("node_classes_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


# def test_node_classes_block_invalid2():
#     """
#     Not OK to have a node-class named Nx.
#     """
#     # Arrange
#     test_string = """
#     node_classes { //
#       node_class Nx(SetDFsToZero, IncrementDFs, CurrentState);
#     }
#     """
#     # Act
#     ast = get_ast("node_classes_block", test_string)
#     with pytest.raises(GeLBExSymbolNotAllowedHere):
#         prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_geometry_block_valid1():
    """
    OK to use Nx inside geometry_block (outside the set_grid_size stmt).
    """
    # Arrange
    test_string = """
    geometry { //
      set_grid_size(32);
      set_grid_periodicity(false);
      nodes[Nx/2 : Nx] = BULK;
    }
    """
    # Act
    ast = get_ast("geometry_block", test_string)
    prevent_clashes_of_symbol_refs_with_implicits(ast)
    pass


def test_geometry_block_invalid1():
    """Invalid, because we refer to x in set_grid_size."""
    # Arrange
    test_string = """
    geometry { //
      set_grid_size(x);
      set_grid_periodicity(false);
      nodes[:] = BULK;
    }
    """
    # Act
    ast = get_ast("geometry_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_geometry_block_invalid2():
    """Invalid, because we refer to x in set_grid_periodicity."""
    # Arrange
    test_string = """
    geometry { //
      set_grid_size(32);
      set_grid_periodicity(x);
      nodes[:] = BULK;
    }
    """
    # Act
    ast = get_ast("geometry_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_geometry_block_invalid3():
    """Invalid, because we refer to x in a paint_nodes_stmte."""
    # Arrange
    test_string = """
    geometry { //
      set_grid_size(32);
      set_grid_periodicity(false);
      nodes[x:] = BULK;
    }
    """
    # Act
    ast = get_ast("geometry_block", test_string)
    with pytest.raises(GeLBExSymbolNotAllowedHere):
        prevent_clashes_of_symbol_refs_with_implicits(ast)
