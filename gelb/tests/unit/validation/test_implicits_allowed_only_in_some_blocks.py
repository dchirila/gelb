#!/usr/bin/env python3

import pytest
from gelb.tests.unit.symbols.symbol_test_utils import assert_symbol_not_allowed_error, get_coordinate_symbols, get_dimension_symbols


class TestImplicitSymbolsInBlocks:
    """Test that implicit symbols are only allowed in appropriate blocks."""
    
    @pytest.mark.parametrize("symbol", get_coordinate_symbols() + get_dimension_symbols())
    def test_global_constants_block_invalid(self, symbol):
        """Invalid: implicit symbols not allowed in global_constants blocks."""
        test_string = f"""
        global_constants {{ //
          const int TUTU = {symbol};
        }}
        """
        assert_symbol_not_allowed_error(test_string, "global_constants_block")

    @pytest.mark.parametrize("symbol", get_coordinate_symbols() + get_dimension_symbols())
    def test_lattices_block_dimension_invalid(self, symbol):
        """Invalid: implicit symbols not allowed in lattice dimension specifications."""
        test_string = f"""
        lattices {{
          lattice myLattice({symbol}, 5, int, 32, false);
        }}
        """
        assert_symbol_not_allowed_error(test_string, "lattices_block")

    @pytest.mark.parametrize("symbol", get_coordinate_symbols() + get_dimension_symbols())
    def test_node_classes_block_invalid(self, symbol):
        """Invalid: implicit symbols not allowed in node_classes blocks."""
        test_string = f"""
        node_classes {{
          node_class my_node_class({symbol}, dyn_fun1, gauge_fun1);
        }}
        """
        assert_symbol_not_allowed_error(test_string, "node_classes_block")

    # Additional lattice tests for Q-value parameters (second dimension parameter)
    @pytest.mark.parametrize("symbol", get_coordinate_symbols() + get_dimension_symbols())
    def test_lattices_block_q_value_invalid(self, symbol):
        """Invalid: implicit symbols not allowed in lattice Q-value specifications."""
        test_string = f"""
        lattices {{ //
          lattice f(2, {symbol}, int, {{32, 32}}, {{false, false}});
        }}
        """
        assert_symbol_not_allowed_error(test_string, "lattices_block")

    def test_geometry_block_invalid_x(self):
        """Invalid: x not allowed in geometry block node painting."""
        test_string = """
        geometry {
          nodes[x] = BULK;
        }
        """
        assert_symbol_not_allowed_error(test_string, "geometry_block")

    def test_geometry_block_invalid_y(self):
        """Invalid: y not allowed in geometry block node painting."""
        test_string = """
        geometry {
          nodes[:, y] = BULK;
        }
        """
        assert_symbol_not_allowed_error(test_string, "geometry_block")

    def test_geometry_block_invalid_z(self):
        """Invalid: z not allowed in geometry block node painting."""
        test_string = """
        geometry {
          nodes[:, :, z] = BULK;
        }
        """
        assert_symbol_not_allowed_error(test_string, "geometry_block")

    def test_geometry_block_valid_Nx(self):
        """Valid: Nx is allowed in geometry block node painting after implicit symbols are added."""
        from gelb.tests.test_utils import get_ast
        from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
        
        test_string = """
        geometry {
          nodes[0:Nx] = BULK;
        }
        """
        # This should not raise any exception since geometry blocks allow Nx references
        ast = get_ast("geometry_block", test_string)
        prevent_clashes_of_symbol_refs_with_implicits(ast)

    def test_geometry_block_valid_Ny(self):
        """Valid: Ny is allowed in geometry block node painting after implicit symbols are added."""
        from gelb.tests.test_utils import get_ast
        from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
        
        test_string = """
        geometry {
          nodes[:, 0:Ny] = BULK;
        }
        """
        # This should not raise any exception since geometry blocks allow Ny references
        ast = get_ast("geometry_block", test_string)
        prevent_clashes_of_symbol_refs_with_implicits(ast)

    def test_geometry_block_valid_Nz(self):
        """Valid: Nz is allowed in geometry block node painting after implicit symbols are added."""
        from gelb.tests.test_utils import get_ast
        from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
        
        test_string = """
        geometry {
          nodes[:, :, 0:Nz] = BULK;
        }
        """
        # This should not raise any exception since geometry blocks allow Nz references
        ast = get_ast("geometry_block", test_string)
        prevent_clashes_of_symbol_refs_with_implicits(ast)

    # Positive tests - cases where symbols should be allowed
    def test_initializer_block_valid1(self):
        """Valid: x is allowed in initializer blocks."""
        from gelb.tests.test_utils import get_ast
        from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
        
        test_string = """
        initializer init_fun1 {
          f.out[x | 0] = 0;
        }
        """
        # This should not raise any exception
        ast = get_ast("initializer_block", test_string)
        prevent_clashes_of_symbol_refs_with_implicits(ast)

    def test_initializer_block_valid2(self):
        """Valid: y is allowed in initializer blocks.""" 
        from gelb.tests.test_utils import get_ast
        from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
        
        test_string = """
        initializer init_fun1 {
          f.out[x, y | 0] = 0;
        }
        """
        # This should not raise any exception
        ast = get_ast("initializer_block", test_string)
        prevent_clashes_of_symbol_refs_with_implicits(ast)

    def test_dynamic_block_valid1(self):
        """Valid: x is allowed in dynamic blocks."""
        from gelb.tests.test_utils import get_ast
        from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
        
        test_string = """
        dynamic dyn_fun1 {
          f.out[x | 0] = f.in[x | 0];
        }
        """
        # This should not raise any exception
        ast = get_ast("dynamic_block", test_string)
        prevent_clashes_of_symbol_refs_with_implicits(ast)

    def test_dynamic_block_valid2(self):
        """Valid: y is allowed in dynamic blocks."""
        from gelb.tests.test_utils import get_ast
        from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
        
        test_string = """
        dynamic dyn_fun1 {
          f.out[x, y | 0] = f.in[x, y | 0];
        }
        """
        # This should not raise any exception
        ast = get_ast("dynamic_block", test_string)
        prevent_clashes_of_symbol_refs_with_implicits(ast)

    def test_gauge_block_valid1(self):
        """Valid: x is allowed in gauge blocks."""
        from gelb.tests.test_utils import get_ast
        from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
        
        test_string = """
        gauge gauge_fun1(out = {int value;}) {
          value = f.in[x | 0];
        }
        """
        # This should not raise any exception
        ast = get_ast("gauge_block", test_string)
        prevent_clashes_of_symbol_refs_with_implicits(ast)

    def test_geometry_block_valid1(self):
        """Valid: basic geometry block without implicit symbols."""
        from gelb.tests.test_utils import get_ast
        from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
        
        test_string = """
        geometry {
          nodes[:] = BULK;
        }
        """
        # This should not raise any exception
        ast = get_ast("geometry_block", test_string)
        prevent_clashes_of_symbol_refs_with_implicits(ast)