#!/usr/bin/env python3
"""
Tests for lattice arithmetic validation after enabling array arithmetic.

These tests ensure that lattice selections can be used in arithmetic operations
as they are fundamentally arrays with distribution functions.
"""

import pytest
from gelb.tests.test_utils import (
    get_typed_ast, get_validated_ast, minimal_gelb_program_1d,
    minimal_gelb_program_2d
)
from gelb.utils.exceptions import GeLBExTypeError


class TestLatticeArithmeticValidation:
    """Test that lattice selections work with arithmetic operations."""
    
    def test_lattice_plus_scalar_1d(self):
        """Test 1D lattice selection + scalar passes validation."""
        test_code = """
simulation_description("1D lattice arithmetic");

lattices {
    lattice f(1, 3, int, 32, false);  // 3 DFs
}

initializer Init {
    f.out[x | :] = 0;
}

dynamic Update {
    f.out[x | :] = f.in[x | :] + 1;  // Should work now!
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
        
        # Should compile without errors
        ast = get_validated_ast(test_code)
        assert ast is not None
        
    def test_lattice_multiply_scalar_2d(self):
        """Test 2D lattice selection * scalar passes validation."""
        test_code = minimal_gelb_program_2d(
            dynamic_content="f.out[x, y | :] = f.in[x, y | :] * 0.5;"
        )
        
        # Should compile without errors
        ast = get_validated_ast(test_code)
        assert ast is not None
        
    def test_lattice_plus_lattice_same_shape(self):
        """Test lattice + lattice with same shape passes validation."""
        test_code = """
simulation_description("Lattice-lattice arithmetic");

lattices {
    lattice f(1, 3, int, 32, false);
    lattice g(1, 3, int, 32, false);
}

initializer Init {
    f.out[x | :] = 1;
    g.out[x | :] = 2;
}

dynamic Update {
    f.out[x | :] = f.in[x | :] + g.in[x | :];  // Same shape arrays
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
        
        # Should compile without errors
        ast = get_validated_ast(test_code)
        assert ast is not None
        
    def test_all_arithmetic_operations_with_lattice(self):
        """Test all arithmetic operations work with lattice selections."""
        test_code = """
simulation_description("All arithmetic ops");

lattices {
    lattice f(1, 3, real, 32, false);
}

initializer Init {
    f.out[x | :] = 10.0;
}

dynamic Update {
    // All of these should work now
    f.out[x | 0] = f.in[x | 0] + 1.0;    // Addition
    f.out[x | 1] = f.in[x | 1] - 0.5;    // Subtraction
    f.out[x | 2] = f.in[x | 2] * 2.0;    // Multiplication
    f.out[x | :] = f.in[x | :] / 2.0;    // Division
}

gauge Output(out = {real val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    nodes[:] = BULK;
}"""
        
        # Should compile without errors
        ast = get_validated_ast(test_code)
        assert ast is not None
        
    def test_lattice_comparison_operations(self):
        """Test comparison operations work with lattice selections."""
        # Use raw program since we need custom gauge output
        test_code = """
simulation_description("Lattice comparison");

lattices {
    lattice f(1, 3, int, 32, false);
}

initializer Init {
    f.out[x | :] = x;
}

dynamic Update {
    f.out[x | :] = f.in[x | :];
}

gauge Output(out = {array[bool, 3] mask;}) {
    mask = f.in[x | :] > 0;  // Array comparison
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    nodes[:] = BULK;
}"""
        
        # Should compile without errors
        ast = get_validated_ast(test_code)
        assert ast is not None
        
    def test_complex_lattice_expression(self):
        """Test complex expressions with lattice selections."""
        # Use raw program to specify real lattice and TAU constant
        test_code = """
simulation_description("Complex lattice expression");

global_constants {
    const real TAU = 0.6;
}

lattices {
    lattice f(1, 3, real, 32, false);
}

initializer Init {
    f.out[x | :] = 1.0;
}

dynamic Update {
    // BGK collision-like expression
    f.out[x | :] = f.in[x | :] + (1.0 - f.in[x | :]) / TAU;
}

gauge Output(out = {real val;}) {
    val = f.in[x | 0];
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    nodes[:] = BULK;
}"""
        
        # Should compile without errors
        ast = get_validated_ast(test_code)
        assert ast is not None