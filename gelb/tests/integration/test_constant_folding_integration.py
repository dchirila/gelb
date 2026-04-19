#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import get_typed_ast
from gelb.midware.stage2_midware import fold_constants
from gelb.gelb_ast.ASTNodes import *


class TestConstantFoldingIntegration:
    """Integration tests for constant folding with full compiler pipeline."""
    
    def test_constant_folding_in_midware_pipeline(self):
        """Test that constant folding works in the midware pipeline."""
        source = """
        simulation_description("Constant folding test");
        
        global_constants {
            const int COMPUTED = 5 + 3;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 10 - 5;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 2 * 3;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        # Process through frontend
        ast = get_typed_ast(source)
        
        # Apply constant folding
        folded_ast = fold_constants(ast)
        
        # Check global constants - COMPUTED should be folded to 8
        const_stmt = folded_ast.global_constants.stmts[0]
        assert isinstance(const_stmt.value, IntLiteral_N)
        assert const_stmt.value.value == 8
        
        # Check initializer - should be folded to 5
        init_stmt = folded_ast.initializers.elements[0].stmts[0]
        assert isinstance(init_stmt.rhs, IntLiteral_N)
        assert init_stmt.rhs.value == 5
        
        # Check dynamic - should be folded to 6
        dynamic_stmt = folded_ast.dynamics.elements[0].stmts[0]
        assert isinstance(dynamic_stmt.rhs, IntLiteral_N)
        assert dynamic_stmt.rhs.value == 6
    
    def test_division_by_zero_setup_for_detection(self):
        """Test that expressions evaluating to zero are folded for division by zero detection."""
        source = """
        simulation_description("Division by zero test");
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 5 - 5;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        # Process through frontend
        ast = get_typed_ast(source)
        
        # Apply constant folding
        folded_ast = fold_constants(ast)
        
        # Check that (5 - 5) is folded to 0
        dynamic_stmt = folded_ast.dynamics.elements[0].stmts[0]
        assert isinstance(dynamic_stmt.rhs, IntLiteral_N)
        assert dynamic_stmt.rhs.value == 0
        
        # This enables division by zero detection to catch expressions like:
        # f.out[x | 0] = 1 / (5 - 5);
        # After constant folding: f.out[x | 0] = 1 / 0;
    
    def test_nested_constant_expressions(self):
        """Test folding of nested constant expressions."""
        source = """
        simulation_description("Nested expressions test");
        
        global_constants {
            const int RESULT = (2 + 3) * (4 - 1);
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 1;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        # Process through frontend
        ast = get_typed_ast(source)
        
        # Apply constant folding
        folded_ast = fold_constants(ast)
        
        # Check that (2+3) * (4-1) = 5 * 3 = 15
        const_stmt = folded_ast.global_constants.stmts[0]
        assert isinstance(const_stmt.value, IntLiteral_N)
        assert const_stmt.value.value == 15
    
    def test_comparison_folding(self):
        """Test folding of comparison expressions."""
        source = """
        simulation_description("Comparison test");
        
        global_constants {
            const bool RESULT = 5 > 3;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 1;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        # Process through frontend
        ast = get_typed_ast(source)
        
        # Apply constant folding
        folded_ast = fold_constants(ast)
        
        # Check that 5 > 3 is folded to true
        const_stmt = folded_ast.global_constants.stmts[0]
        assert isinstance(const_stmt.value, BoolLiteral_N)
        assert const_stmt.value.value == 'true'
    
    def test_mixed_types_folding(self):
        """Test folding with mixed integer and real types."""
        source = """
        simulation_description("Mixed types test");
        
        global_constants {
            const real RESULT = 5 + 2.5;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 1;
        }
        
        gauge TestGauge -> (real rho) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        # Process through frontend
        ast = get_typed_ast(source)
        
        # Apply constant folding
        folded_ast = fold_constants(ast)
        
        # Check that 5 + 2.5 is folded to 7.5
        const_stmt = folded_ast.global_constants.stmts[0]
        assert isinstance(const_stmt.value, RealLiteral_N)
        assert const_stmt.value.value == 7.5