#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import minimal_gelb_program_1d
from gelb.frontend.stage1_frontend import (
    get_ast, validate_ast_root_is_program, validate_gauges
)
from gelb.utils.exceptions import GeLBExTypeError


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
        gauge ValidGauge(out = {int result; real value;}) {
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
        validate_gauges(ast)
    
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
        gauge InvalidGauge() {
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
            validate_gauges(ast)
        
        assert "InvalidGauge" in str(exc_info.value)
        assert "no output specification" in str(exc_info.value)
        assert "out = {" in str(exc_info.value)  # Hint should mention syntax
    
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
        gauge EmptyGauge(out = {}) {
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
            validate_gauges(ast)
        
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
        gauge ValidGauge(out = {int result;}) {
            result = 42;
        }
        gauge InvalidGauge() {
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
            validate_gauges(ast)
        
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
        gauge UnassignedGauge(out = {int result; real value;}) {
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
            validate_gauges(ast)
        
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
        gauge PartialGauge(out = {int result; real value;}) {
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
            validate_gauges(ast)
        
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
        gauge CompleteGauge(out = {int result; real value;}) {
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
        validate_gauges(ast)