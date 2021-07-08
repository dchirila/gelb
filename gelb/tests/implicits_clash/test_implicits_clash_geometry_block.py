#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import (
    ASTBuilderVisitor,
    get_ast,
    prevent_clashes_of_symbol_refs_with_implicits
)
from gelb.utils.exceptions import (
    GeLBExSyntaxError
)


def test_invalid1():
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
    with pytest.raises(GeLBExSyntaxError):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_invalid2():
    """Invalid, because we refer to x in set_grid_size."""
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
    with pytest.raises(GeLBExSyntaxError):
        prevent_clashes_of_symbol_refs_with_implicits(ast)


def test_invalid3():
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
    with pytest.raises(GeLBExSyntaxError):
        prevent_clashes_of_symbol_refs_with_implicits(ast)
