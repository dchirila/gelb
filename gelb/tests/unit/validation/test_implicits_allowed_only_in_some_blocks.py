#!/usr/bin/env python3

import pytest
from gelb.tests.unit.symbols.symbol_test_utils import assert_symbol_not_allowed_error, get_coordinate_symbols, get_dimension_symbols, get_timestep_symbol


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

    @pytest.mark.parametrize("symbol", get_timestep_symbol())
    def test_global_constants_block_invalid_t(self, symbol):
        """Invalid: implicit timestep `t` not allowed in global_constants."""
        test_string = f"""
        global_constants {{ //
          const int TUTU = {symbol};
        }}
        """
        assert_symbol_not_allowed_error(test_string, "global_constants_block")

    @pytest.mark.parametrize("symbol", get_timestep_symbol())
    def test_lattices_block_invalid_t(self, symbol):
        """Invalid: implicit timestep `t` not allowed in lattice parameters."""
        test_string = f"""
        lattices {{
          lattice f(1, {symbol}, int, 32, false);
        }}
        """
        assert_symbol_not_allowed_error(test_string, "lattices_block")

    @pytest.mark.parametrize("symbol", get_timestep_symbol())
    def test_node_classes_block_invalid_t(self, symbol):
        """Invalid: implicit timestep `t` not allowed in node_classes."""
        test_string = f"""
        node_classes {{
          node_class my_nc({symbol}, dyn_fun1, gauge_fun1);
        }}
        """
        assert_symbol_not_allowed_error(test_string, "node_classes_block")

    def test_geometry_block_invalid_t(self):
        """Invalid: implicit timestep `t` not allowed in geometry."""
        test_string = """
        geometry {
          nodes[t] = BULK;
        }
        """
        assert_symbol_not_allowed_error(test_string, "geometry_block")

    def test_geometry_block_coordinates_pass_the_clash_check(self):
        """x, y, z are predicate inputs in the geometry block: the implicit
        clash check lets them through (a where predicate needs them); their
        misuse in a range or point paint is reported by the fixed-geometry
        validator, tested below and in test_conditional_paint.py."""
        from gelb.tests.test_utils import get_ast
        from gelb.frontend.stage1_frontend import prevent_clashes_of_symbol_refs_with_implicits
        for paint in ("nodes[where x < 2] = BULK;",
                      "nodes[where x < 2 && y > 1] = BULK;",
                      "nodes[where z == 0] = BULK;"):
            ast = get_ast("geometry_block", f"geometry {{ {paint} }}")
            prevent_clashes_of_symbol_refs_with_implicits(ast)  # no error

    @pytest.mark.parametrize("paint", [
        "nodes[x] = BULK;",
        "nodes[:, y] = BULK;",
        "nodes[:, :, z] = BULK;",
    ])
    def test_geometry_block_coordinates_rejected_in_range_paints(self, paint):
        """Invalid: a coordinate in a range or point paint (only a where
        predicate may use them)."""
        from gelb.compiler_pipeline import (
            PipelineOptions, PipelineProfile, compile_source)
        from gelb.utils.exceptions import GeLBExTypeError
        d = paint.count(",") + 1
        coords = ", ".join("xyz"[:d])
        size = "{" + ", ".join(["8"] * d) + "}" if d > 1 else "8"
        per = "{" + ", ".join(["false"] * d) + "}" if d > 1 else "false"
        colons = ", ".join([":"] * d)
        program = f"""
        simulation_description("t");
        lattices {{ lattice f({d}, 1, int, {size}, {per}); }}
        initializer I {{ f.out[{coords} | 0] = 0; }}
        dynamic D {{ f.out[{coords} | 0] = f.in[{coords} | 0]; }}
        gauge G -> (int v) {{ v = f.in[{coords} | 0]; }}
        node_classes {{ node_class BULK(I, D, G); }}
        geometry {{ nodes[{colons}] = BULK; {paint} }}
        """
        with pytest.raises(GeLBExTypeError) as info:
            compile_source(program, PipelineProfile.DIAGNOSTICS,
                           PipelineOptions(require_stencils=True, require_geometry=True))
        assert "only inside a 'where' predicate" in str(info.value)

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
        gauge gauge_fun1 -> (int value) {
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


class TestImplicitSymbolsInFunctions:
    """
    Functions inherit global compile-time constants, but not per-site runtime
    variables.

    As a result, function definitions must not shadow Nx/Ny/Nz, but may use
    x/y/z/t as ordinary parameter or local names. Geometry conditional-paint
    predicates commonly name positional coordinate arguments x/y.
    """

    @pytest.mark.parametrize("symbol", get_coordinate_symbols() + get_timestep_symbol())
    def test_function_input_parameter_runtime_names_allowed(self, symbol):
        """Function input parameters may be named x/y/z/t."""
        from gelb.frontend.stage1_frontend import (
            get_ast, build_symbols_tables,
            prevent_clashes_of_symbol_defs_with_implicits,
        )
        from gelb.utils import config

        code = f"""
        simulation_description("test");
        lattices {{ lattice f(1, 1, int, 32, false); }}
        function Foo(int {symbol}) -> (int result) {{
            result = {symbol} + 1;
        }}
        initializer Init {{ f.out[x | 0] = 0; }}
        dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
        gauge Out -> (int val) {{ val = f.in[x | 0]; }}
        node_classes {{ node_class BULK(Init, Dyn, Out); }}
        geometry {{ nodes[:] = BULK; }}
        """
        config.GELB_SRC_RAW = code
        ast = get_ast("gelb_program", code)
        ast = build_symbols_tables(ast)
        prevent_clashes_of_symbol_defs_with_implicits(ast)

    @pytest.mark.parametrize("symbol", get_coordinate_symbols() + get_timestep_symbol())
    def test_function_output_parameter_runtime_names_allowed(self, symbol):
        """Function output parameters may be named x/y/z/t."""
        from gelb.frontend.stage1_frontend import (
            get_ast, build_symbols_tables,
            prevent_clashes_of_symbol_defs_with_implicits,
        )
        from gelb.utils import config

        code = f"""
        simulation_description("test");
        lattices {{ lattice f(1, 1, int, 32, false); }}
        function Foo(int a) -> (int {symbol}) {{
            {symbol} = a + 1;
        }}
        initializer Init {{ f.out[x | 0] = 0; }}
        dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
        gauge Out -> (int val) {{ val = f.in[x | 0]; }}
        node_classes {{ node_class BULK(Init, Dyn, Out); }}
        geometry {{ nodes[:] = BULK; }}
        """
        config.GELB_SRC_RAW = code
        ast = get_ast("gelb_program", code)
        ast = build_symbols_tables(ast)
        prevent_clashes_of_symbol_defs_with_implicits(ast)

    @pytest.mark.parametrize("symbol", get_coordinate_symbols() + get_timestep_symbol())
    def test_function_local_runtime_names_allowed(self, symbol):
        """Local variables inside functions may be named x/y/z/t."""
        from gelb.frontend.stage1_frontend import (
            get_ast, build_symbols_tables,
            prevent_clashes_of_symbol_defs_with_implicits,
        )
        from gelb.utils import config

        code = f"""
        simulation_description("test");
        lattices {{ lattice f(1, 1, int, 32, false); }}
        function Foo(int a) -> (int result) {{
            int {symbol};
            {symbol} = a + 1;
            result = {symbol};
        }}
        initializer Init {{ f.out[x | 0] = 0; }}
        dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
        gauge Out -> (int val) {{ val = f.in[x | 0]; }}
        node_classes {{ node_class BULK(Init, Dyn, Out); }}
        geometry {{ nodes[:] = BULK; }}
        """
        config.GELB_SRC_RAW = code
        ast = get_ast("gelb_program", code)
        ast = build_symbols_tables(ast)
        prevent_clashes_of_symbol_defs_with_implicits(ast)

    @pytest.mark.parametrize("symbol", get_dimension_symbols())
    def test_function_input_parameter_dimension_name_rejected(self, symbol):
        """Function input parameters may not shadow Nx/Ny/Nz."""
        from gelb.frontend.stage1_frontend import (
            get_ast, build_symbols_tables,
            prevent_clashes_of_symbol_defs_with_implicits,
        )
        from gelb.utils import config
        from gelb.utils.exceptions import GeLBExSyntaxError

        code = f"""
        simulation_description("test");
        lattices {{ lattice f(1, 1, int, 32, false); }}
        function Foo(int {symbol}) -> (int result) {{
            result = {symbol} + 1;
        }}
        initializer Init {{ f.out[x | 0] = 0; }}
        dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
        gauge Out -> (int val) {{ val = f.in[x | 0]; }}
        node_classes {{ node_class BULK(Init, Dyn, Out); }}
        geometry {{ nodes[:] = BULK; }}
        """
        config.GELB_SRC_RAW = code
        ast = get_ast("gelb_program", code)
        ast = build_symbols_tables(ast)
        with pytest.raises(GeLBExSyntaxError):
            prevent_clashes_of_symbol_defs_with_implicits(ast)

    @pytest.mark.parametrize("symbol", get_dimension_symbols())
    def test_function_output_parameter_dimension_name_rejected(self, symbol):
        """Function output parameters may not shadow Nx/Ny/Nz."""
        from gelb.frontend.stage1_frontend import (
            get_ast, build_symbols_tables,
            prevent_clashes_of_symbol_defs_with_implicits,
        )
        from gelb.utils import config
        from gelb.utils.exceptions import GeLBExSyntaxError

        code = f"""
        simulation_description("test");
        lattices {{ lattice f(1, 1, int, 32, false); }}
        function Foo(int a) -> (int {symbol}) {{
            {symbol} = a + 1;
        }}
        initializer Init {{ f.out[x | 0] = 0; }}
        dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
        gauge Out -> (int val) {{ val = f.in[x | 0]; }}
        node_classes {{ node_class BULK(Init, Dyn, Out); }}
        geometry {{ nodes[:] = BULK; }}
        """
        config.GELB_SRC_RAW = code
        ast = get_ast("gelb_program", code)
        ast = build_symbols_tables(ast)
        with pytest.raises(GeLBExSyntaxError):
            prevent_clashes_of_symbol_defs_with_implicits(ast)

    @pytest.mark.parametrize("symbol", get_dimension_symbols())
    def test_function_local_dimension_name_rejected(self, symbol):
        """Local variables inside functions may not shadow Nx/Ny/Nz."""
        from gelb.frontend.stage1_frontend import (
            get_ast, build_symbols_tables,
            prevent_clashes_of_symbol_defs_with_implicits,
        )
        from gelb.utils import config
        from gelb.utils.exceptions import GeLBExSyntaxError

        code = f"""
        simulation_description("test");
        lattices {{ lattice f(1, 1, int, 32, false); }}
        function Foo(int a) -> (int result) {{
            int {symbol};
            {symbol} = a + 1;
            result = {symbol};
        }}
        initializer Init {{ f.out[x | 0] = 0; }}
        dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
        gauge Out -> (int val) {{ val = f.in[x | 0]; }}
        node_classes {{ node_class BULK(Init, Dyn, Out); }}
        geometry {{ nodes[:] = BULK; }}
        """
        config.GELB_SRC_RAW = code
        ast = get_ast("gelb_program", code)
        ast = build_symbols_tables(ast)
        with pytest.raises(GeLBExSyntaxError):
            prevent_clashes_of_symbol_defs_with_implicits(ast)

    def test_function_called_with_implicit_coordinate_still_allowed(self):
        """A function may accept x as an argument under a non-reserved name."""
        from gelb.frontend.stage1_frontend import (
            get_ast, build_symbols_tables,
            prevent_clashes_of_symbol_defs_with_implicits,
        )
        from gelb.utils import config

        code = """
        simulation_description("test");
        lattices { lattice f(2, 1, int, {32, 32}, {false, false}); }
        function AddOne(int coord) -> (int result) {
            result = coord + 1;
        }
        initializer Init { f.out[x, y | 0] = AddOne(x); }
        dynamic Dyn { f.out[x, y | 0] = f.in[x, y | 0]; }
        gauge Out -> (int val) { val = f.in[x, y | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:,:] = BULK; }
        """
        config.GELB_SRC_RAW = code
        ast = get_ast("gelb_program", code)
        ast = build_symbols_tables(ast)
        prevent_clashes_of_symbol_defs_with_implicits(ast)


class TestImplicitSymbolsRejectedInDefinitions:
    """
    Verify that definitions are rejected where implicit names would collide
    with language-level names. Global definitions and per-site blocks reserve
    all implicit names; functions reserve only globally visible Nx/Ny/Nz.
    """

    @pytest.mark.parametrize(
        "symbol",
        get_coordinate_symbols() + get_dimension_symbols() + get_timestep_symbol()
    )
    def test_global_constants_implicit_name_definition_rejected(self, symbol):
        """Cannot define a global constant with an implicit name."""
        from gelb.frontend.stage1_frontend import (
            get_ast, build_symbols_tables,
            prevent_clashes_of_symbol_defs_with_implicits,
        )
        from gelb.utils import config
        from gelb.utils.exceptions import GeLBExSyntaxError

        code = f"""
        simulation_description("test");
        global_constants {{ const int {symbol} = 5; }}
        lattices {{ lattice f(1, 1, int, 32, false); }}
        initializer Init {{ f.out[x | 0] = 0; }}
        dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
        gauge Out -> (int val) {{ val = f.in[x | 0]; }}
        node_classes {{ node_class BULK(Init, Dyn, Out); }}
        geometry {{ nodes[:] = BULK; }}
        """
        config.GELB_SRC_RAW = code
        ast = get_ast("gelb_program", code)
        ast = build_symbols_tables(ast)
        with pytest.raises(GeLBExSyntaxError):
            prevent_clashes_of_symbol_defs_with_implicits(ast)

    @pytest.mark.parametrize(
        "symbol",
        get_coordinate_symbols() + get_dimension_symbols() + get_timestep_symbol()
    )
    def test_initializer_local_var_definition_rejected(self, symbol):
        """Cannot define an implicit name as a local variable in an initializer."""
        from gelb.frontend.stage1_frontend import (
            get_ast, build_symbols_tables,
            prevent_clashes_of_symbol_defs_with_implicits,
        )
        from gelb.utils import config
        from gelb.utils.exceptions import GeLBExSyntaxError

        code = f"""
        simulation_description("test");
        lattices {{ lattice f(1, 1, int, 32, false); }}
        initializer Init {{ int {symbol}; {symbol} = 5; f.out[x | 0] = 0; }}
        dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
        gauge Out -> (int val) {{ val = f.in[x | 0]; }}
        node_classes {{ node_class BULK(Init, Dyn, Out); }}
        geometry {{ nodes[:] = BULK; }}
        """
        config.GELB_SRC_RAW = code
        ast = get_ast("gelb_program", code)
        ast = build_symbols_tables(ast)
        with pytest.raises(GeLBExSyntaxError):
            prevent_clashes_of_symbol_defs_with_implicits(ast)

    @pytest.mark.parametrize(
        "symbol",
        get_coordinate_symbols() + get_dimension_symbols() + get_timestep_symbol()
    )
    def test_gauge_output_var_definition_rejected(self, symbol):
        """Cannot name a gauge output variable with an implicit name."""
        from gelb.frontend.stage1_frontend import (
            get_ast, build_symbols_tables,
            prevent_clashes_of_symbol_defs_with_implicits,
        )
        from gelb.utils import config
        from gelb.utils.exceptions import GeLBExSyntaxError

        code = f"""
        simulation_description("test");
        lattices {{ lattice f(1, 1, int, 32, false); }}
        initializer Init {{ f.out[x | 0] = 0; }}
        dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
        gauge Out -> (int {symbol}) {{ {symbol} = f.in[x | 0]; }}
        node_classes {{ node_class BULK(Init, Dyn, Out); }}
        geometry {{ nodes[:] = BULK; }}
        """
        config.GELB_SRC_RAW = code
        ast = get_ast("gelb_program", code)
        ast = build_symbols_tables(ast)
        with pytest.raises(GeLBExSyntaxError):
            prevent_clashes_of_symbol_defs_with_implicits(ast)
