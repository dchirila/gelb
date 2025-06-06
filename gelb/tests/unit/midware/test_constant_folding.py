#!/usr/bin/env python3

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
from gelb.tests.test_utils import get_typed_ast


class TestConstantFoldingWithPipeline:
    """Test constant folding integrated with full compilation pipeline."""
    
    def test_global_constants_folding(self):
        """Test folding in global constant definitions."""
        source = """
        simulation_description("Test constant folding");
        
        global_constants {
            const int A = 5 + 3;
            const int B = 10 - 2;
            const int C = 4 * 5;
            const real D = 15.0 / 3.0;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = A;
        }
        
        gauge TestGauge(out = {real rho;}) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        # Check that global constants were folded
        const_stmts = folded_ast.global_constants.stmts
        
        # A = 5 + 3 = 8
        assert isinstance(const_stmts[0].value, IntLiteral_N)
        assert const_stmts[0].value.value == 8
        
        # B = 10 - 2 = 8  
        assert isinstance(const_stmts[1].value, IntLiteral_N)
        assert const_stmts[1].value.value == 8
        
        # C = 4 * 5 = 20
        assert isinstance(const_stmts[2].value, IntLiteral_N)
        assert const_stmts[2].value.value == 20
        
        # D = 15.0 / 3.0 = 5.0
        assert isinstance(const_stmts[3].value, RealLiteral_N)
        assert const_stmts[3].value.value == 5.0
    
    def test_nested_expressions_folding(self):
        """Test folding of nested constant expressions."""
        source = """
        simulation_description("Test nested folding");
        
        global_constants {
            const int NESTED = (2 + 3) * (4 - 1);
            const bool COMPARISON = 5 > 3;
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
        
        gauge TestGauge(out = {real rho;}) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        const_stmts = folded_ast.global_constants.stmts
        
        # NESTED = (2+3) * (4-1) = 5 * 3 = 15
        assert isinstance(const_stmts[0].value, IntLiteral_N)
        assert const_stmts[0].value.value == 15
        
        # COMPARISON = 5 > 3 = true
        assert isinstance(const_stmts[1].value, BoolLiteral_N)
        assert const_stmts[1].value.value == 'true'
    
    def test_zero_result_for_division_detection(self):
        """Test that expressions evaluating to zero are folded (enables division by zero detection)."""
        source = """
        simulation_description("Test zero folding for division detection");
        
        global_constants {
            const int ZERO_RESULT = 5 - 5;
            const int ANOTHER_ZERO = 10 - 5 - 5;
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
        
        gauge TestGauge(out = {real rho;}) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        const_stmts = folded_ast.global_constants.stmts
        
        # Both should fold to 0, enabling division by zero detection
        assert isinstance(const_stmts[0].value, IntLiteral_N)
        assert const_stmts[0].value.value == 0
        
        assert isinstance(const_stmts[1].value, IntLiteral_N)
        assert const_stmts[1].value.value == 0
    
    def test_mixed_type_folding(self):
        """Test folding with mixed integer and real types."""
        source = """
        simulation_description("Test mixed type folding");
        
        global_constants {
            const real MIXED = 5 + 2.5;
            const real INT_DIV = 10 / 4;
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
        
        gauge TestGauge(out = {real rho;}) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        const_stmts = folded_ast.global_constants.stmts
        
        # MIXED = 5 + 2.5 = 7.5
        assert isinstance(const_stmts[0].value, RealLiteral_N)
        assert const_stmts[0].value.value == 7.5
        
        # INT_DIV = 10 / 4 = 2.5 (division always produces real)
        assert isinstance(const_stmts[1].value, RealLiteral_N)
        assert const_stmts[1].value.value == 2.5
    
    def test_division_by_zero_not_folded(self):
        """Test that division by zero is preserved for validation to catch."""
        source = """
        simulation_description("Test division by zero preservation");
        
        global_constants {
            const int SAFE = 10 / 2;
        }
        
        lattices {
            lattice f(1, 3, real, 16, true);
        }
        
        initializer TestInit {
            f.out[x | 0] = 1 / 0;
        }
        
        dynamic TestDynamic {
            f.out[x | 0] = 1;
        }
        
        gauge TestGauge(out = {real rho;}) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        # Check that safe division is folded
        const_stmt = folded_ast.global_constants.stmts[0]
        assert isinstance(const_stmt.value, RealLiteral_N)
        assert const_stmt.value.value == 5.0
        
        # Check that division by zero in initializer is NOT folded (remains as Div_N)
        init_stmt = folded_ast.initializers.elements[0].stmts[0]
        assert isinstance(init_stmt.rhs, Div_N)
        assert isinstance(init_stmt.rhs.left, IntLiteral_N)
        assert isinstance(init_stmt.rhs.right, IntLiteral_N)
        assert init_stmt.rhs.left.value == 1
        assert init_stmt.rhs.right.value == 0


class TestConstantFoldingEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_unary_minus_folding(self):
        """Test folding of unary minus operations."""
        source = """
        simulation_description("Test unary minus folding");
        
        global_constants {
            const int NEG_INT = -42;
            const real NEG_REAL = -3.14;
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
        
        gauge TestGauge(out = {real rho;}) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        const_stmts = folded_ast.global_constants.stmts
        
        # NEG_INT = -42
        assert isinstance(const_stmts[0].value, IntLiteral_N)
        assert const_stmts[0].value.value == -42
        
        # NEG_REAL = -3.14
        assert isinstance(const_stmts[1].value, RealLiteral_N)
        assert const_stmts[1].value.value == -3.14
    
    def test_logical_operations_folding(self):
        """Test folding of logical operations."""
        source = """
        simulation_description("Test logical folding");
        
        global_constants {
            const bool AND_RESULT = true && false;
            const bool OR_RESULT = false || true;
            const bool NOT_RESULT = !true;
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
        
        gauge TestGauge(out = {real rho;}) {
            rho = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(TestInit, TestDynamic, TestGauge);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        """
        
        ast = get_typed_ast(source)
        
        folder = ConstantFoldingVisitor()
        folded_ast = folder.visit(ast, ast)
        
        const_stmts = folded_ast.global_constants.stmts
        
        # AND_RESULT = true && false = false
        assert isinstance(const_stmts[0].value, BoolLiteral_N)
        assert const_stmts[0].value.value == 'false'
        
        # OR_RESULT = false || true = true
        assert isinstance(const_stmts[1].value, BoolLiteral_N)
        assert const_stmts[1].value.value == 'true'
        
        # NOT_RESULT = !true = false
        assert isinstance(const_stmts[2].value, BoolLiteral_N)
        assert const_stmts[2].value.value == 'false'