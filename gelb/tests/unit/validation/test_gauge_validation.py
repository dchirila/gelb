#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import minimal_gelb_program_1d
from gelb.frontend.stage1_frontend import (
    build_symbols_tables, get_ast, validate_ast_root_is_program,
    validate_block_signatures
)
from gelb.utils.exceptions import GeLBException, GeLBExTypeError


class TestGaugeValidation:
    """Test gauge validation for output specifications."""
    
    def test_valid_gauge_with_outputs(self):
        """Test that valid gauges with outputs pass validation."""
        test_code = """
        simulation_description("Test");
        lattices {
            lattice f(1, 1, int, 32, false);
        }
        initializer Init {
            f.out[x | 0] = 0;
        }
        dynamic Update {
            f.out[x | 0] = 1;
        }
        gauge ValidGauge -> (int result, real value) {
            result = 42;
            value = 3.14;
        }
        node_classes {
            node_class BULK(Init, Update, ValidGauge);
        }
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_ast("gelb_program", test_code)
        validate_ast_root_is_program(ast)
        
        # Should not raise any exceptions
        validate_block_signatures(ast)
    
    def test_invalid_gauge_no_outputs(self):
        """Test that gauges without output specifications are rejected."""
        test_code = """
        simulation_description("Test");
        lattices {
            lattice f(1, 1, int, 32, false);
        }
        initializer Init {
            f.out[x | 0] = 0;
        }
        dynamic Update {
            f.out[x | 0] = 1;
        }
        gauge InvalidGauge {
            int temp;
            temp = 42;
        }
        node_classes {
            node_class BULK(Init, Update, InvalidGauge);
        }
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_ast("gelb_program", test_code)
        validate_ast_root_is_program(ast)
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_block_signatures(ast)
        
        assert "InvalidGauge" in str(exc_info.value)
        assert "no output specification" in str(exc_info.value)
        assert "-> (type name, ...)" in str(exc_info.value)
    
    def test_invalid_gauge_empty_outputs(self):
        """Test that gauges with empty output specifications are rejected."""
        test_code = """
        simulation_description("Test");
        lattices {
            lattice f(1, 1, int, 32, false);
        }
        initializer Init {
            f.out[x | 0] = 0;
        }
        dynamic Update {
            f.out[x | 0] = 1;
        }
        gauge EmptyGauge -> () {
            int temp;
            temp = 42;
        }
        node_classes {
            node_class BULK(Init, Update, EmptyGauge);
        }
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_ast("gelb_program", test_code)
        validate_ast_root_is_program(ast)
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_block_signatures(ast)
        
        assert "EmptyGauge" in str(exc_info.value)
        assert "no output specification" in str(exc_info.value)
    
    def test_multiple_gauges_validation(self):
        """Test validation with multiple gauges where some are invalid."""
        test_code = """
        simulation_description("Test");
        lattices {
            lattice f(1, 1, int, 32, false);
        }
        initializer Init {
            f.out[x | 0] = 0;
        }
        dynamic Update {
            f.out[x | 0] = 1;
        }
        gauge ValidGauge -> (int result) {
            result = 42;
        }
        gauge InvalidGauge {
            int temp;
            temp = 42;
        }
        node_classes {
            node_class BULK(Init, Update, ValidGauge);
        }
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_ast("gelb_program", test_code)
        validate_ast_root_is_program(ast)
        
        # Should fail on the first invalid gauge encountered
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_block_signatures(ast)
        
        assert "InvalidGauge" in str(exc_info.value)
    
    def test_gauge_with_unassigned_outputs(self):
        """Test that gauges with unassigned output variables are rejected."""
        test_code = """
        simulation_description("Test");
        lattices {
            lattice f(1, 1, int, 32, false);
        }
        initializer Init {
            f.out[x | 0] = 0;
        }
        dynamic Update {
            f.out[x | 0] = 1;
        }
        gauge UnassignedGauge -> (int result, real value) {
            int temp;
            temp = 42;
        }
        node_classes {
            node_class BULK(Init, Update, UnassignedGauge);
        }
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_ast("gelb_program", test_code)
        validate_ast_root_is_program(ast)
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_block_signatures(ast)
        
        assert "UnassignedGauge" in str(exc_info.value)
        assert "declares output variables" in str(exc_info.value)
        assert "but never assigns to them" in str(exc_info.value)
        assert "result" in str(exc_info.value)
        assert "value" in str(exc_info.value)
    
    def test_gauge_with_partially_assigned_outputs(self):
        """Test that gauges with some unassigned output variables are rejected."""
        test_code = """
        simulation_description("Test");
        lattices {
            lattice f(1, 1, int, 32, false);
        }
        initializer Init {
            f.out[x | 0] = 0;
        }
        dynamic Update {
            f.out[x | 0] = 1;
        }
        gauge PartialGauge -> (int result, real value) {
            result = 42;
        }
        node_classes {
            node_class BULK(Init, Update, PartialGauge);
        }
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_ast("gelb_program", test_code)
        validate_ast_root_is_program(ast)
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_block_signatures(ast)
        
        assert "PartialGauge" in str(exc_info.value)
        assert "declares output variable 'value'" in str(exc_info.value)
        assert "but never assigns to it" in str(exc_info.value)
        # Should not mention 'result' since it is assigned
        assert "result" not in str(exc_info.value).split("declares")[1]
    
    def test_gauge_with_all_outputs_assigned(self):
        """Test that gauges with all outputs assigned pass validation."""
        test_code = """
        simulation_description("Test");
        lattices {
            lattice f(1, 1, int, 32, false);
        }
        initializer Init {
            f.out[x | 0] = 0;
        }
        dynamic Update {
            f.out[x | 0] = 1;
        }
        gauge CompleteGauge -> (int result, real value) {
            result = 42;
            value = 3.14;
        }
        node_classes {
            node_class BULK(Init, Update, CompleteGauge);
        }
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_ast("gelb_program", test_code)
        validate_ast_root_is_program(ast)
        
        # Should not raise any exceptions
        validate_block_signatures(ast)


class TestFunctionResultValidation:
    """Test that every function declares at least one named result."""

    @staticmethod
    def _program_with_function(function_source):
        return minimal_gelb_program_1d().replace(
            "node_classes {",
            f"{function_source}\nnode_classes {{",
        )

    def test_function_with_named_result_passes(self):
        ast = get_ast(
            "gelb_program",
            self._program_with_function(
                "function Valid(int value) -> (int result) "
                "{ result = value; }"
            ),
        )

        validate_block_signatures(ast)

    def test_function_without_results_is_rejected(self):
        ast = get_ast(
            "gelb_program",
            self._program_with_function(
                "function Invalid() -> () { int unused; }"
            ),
        )

        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_block_signatures(ast)

        message = str(exc_info.value)
        assert "Function 'Invalid' has no results" in message
        assert "one result is used as an expression" in message
        assert "several results is used with destructuring" in message


class TestSharedOutputTypes:
    """Gauges share an output by its name, one field of the output file
    (user manual, GeLB in 10 minutes: Node classes and geometry), so
    every gauge that declares it must give it one type; ``int64`` is
    ``int`` and ``real64`` is ``real``.  Every declared gauge counts."""

    PROGRAM = """
simulation_description("Test");
lattices {{ lattice f(1, 1, real, 32, false); }}
initializer Init {{ f.out[x | 0] = 0.0; }}
dynamic Update {{ f.out[x | 0] = f.in[x | 0]; }}
gauge GA -> ({first} v) {{ v = 0; }}
gauge GB -> ({second} {name}) {{ {name} = 0; }}
node_classes {{
    node_class A(Init, Update, GA);
    node_class B(Init, Update, {b_gauge});
}}
geometry {{
    nodes[:] = A;
    nodes[0:15] = B;
}}
"""

    TYPES = ("bool", "int8", "int16", "int32", "int", "int64",
             "real32", "real", "real64")
    # The types a shared output may mix: each alias with its type.
    ONE_TYPE = {"int64": "int", "real64": "real"}

    @classmethod
    def _source(cls, first, second, name="v", b_gauge="GB"):
        return cls.PROGRAM.format(
            first=first, second=second, name=name, b_gauge=b_gauge)

    @staticmethod
    def _validate(source):
        ast = get_ast("gelb_program", source)
        validate_ast_root_is_program(ast)
        validate_block_signatures(ast)
        return ast

    @staticmethod
    def _replace(source, old, new):
        assert source.count(old) == 1, old
        return source.replace(old, new)

    @pytest.mark.parametrize("second", TYPES)
    @pytest.mark.parametrize("first", TYPES)
    def test_a_shared_output_has_one_type(self, first, second):
        source = self._source(first, second)
        if self.ONE_TYPE.get(first, first) == self.ONE_TYPE.get(second, second):
            self._validate(source)
            return
        ast = get_ast("gelb_program", source)
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_block_signatures(ast)
        assert str(exc_info.value).startswith(
            f"Gauge 'GB' declares output 'v' as {second}, but gauge 'GA' "
            f"declares it as {first}")
        # The diagnostic points at the second gauge's declaration.
        assert exc_info.value.node is ast.gauges[1].outputs.elements[0]

    @pytest.mark.parametrize("first, second, common", [
        ("int", "real", "real"), ("real", "int", "real"),
        ("bool", "int", "int"), ("bool", "real", "real"),
        ("int8", "int16", "int16"), ("real32", "real64", "real64"),
    ])
    def test_the_hint_suggests_the_common_type(self, first, second, common):
        with pytest.raises(GeLBExTypeError) as exc_info:
            self._validate(self._source(first, second))
        assert f"Declare it as {common} in both gauges" in str(exc_info.value)

    def test_the_diagnostic_points_at_the_mismatching_output(self):
        source = self._replace(
            self._source("int", "real"), "gauge GB -> (real v) { v = 0; }",
            "gauge GB -> (int a, real v) { a = 0; v = 0; }")
        ast = get_ast("gelb_program", source)
        with pytest.raises(GeLBExTypeError) as exc_info:
            validate_block_signatures(ast)
        assert exc_info.value.node is ast.gauges[1].outputs.elements[1]

    def test_different_names_may_have_different_types(self):
        self._validate(self._source("int", "real", name="w"))

    def test_a_gauge_that_no_class_uses_counts(self):
        with pytest.raises(GeLBExTypeError, match="Gauge 'GB' declares"):
            self._validate(self._source("real", "int", b_gauge="GA"))

    def test_the_first_declaration_sets_the_type(self):
        source = self._replace(
            self._source("real", "real64"), "node_classes {",
            "gauge GC -> (int v) { v = 0; }\nnode_classes {")
        source = self._replace(
            source, "node_class B(Init, Update, GB);",
            "node_class B(Init, Update, GB);\n    node_class C(Init, Update, GC);")
        source = self._replace(
            source, "nodes[0:15] = B;", "nodes[0:15] = B;\n    nodes[16:20] = C;")
        with pytest.raises(GeLBExTypeError) as exc_info:
            self._validate(source)
        assert str(exc_info.value).startswith(
            "Gauge 'GC' declares output 'v' as int, but gauge 'GA' "
            "declares it as real")

    @pytest.mark.parametrize("old, new", [
        # A name repeated in the first gauge, the second one of its types.
        ("gauge GA -> (int v) { v = 0; }",
         "gauge GA -> (int v, real v) { v = 0; }"),
        # A name repeated in the second gauge.
        ("gauge GB -> (real v) { v = 0; }",
         "gauge GB -> (int v, real v) { v = 0; }"),
        # Two gauges of one name, and a third gauge that differs.
        ("gauge GB -> (real v) { v = 0; }",
         "gauge GA -> (int v) { v = 0; }\ngauge GB -> (real v) { v = 0; }"),
        # Two gauges of one name that differ.
        ("gauge GB -> (real v) { v = 0; }",
         "gauge GA -> (real v) { v = 0; }"),
    ])
    def test_a_repeated_name_is_left_to_the_symbol_table(self, old, new):
        source = self._replace(self._source("int", "real"), old, new)
        ast = self._validate(source)
        with pytest.raises(GeLBException, match="already"):
            build_symbols_tables(ast)
