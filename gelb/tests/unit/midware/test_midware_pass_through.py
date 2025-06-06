#!/usr/bin/env python3
"""
Unit tests for midware pass-through functionality.

Tests the minimal midware implementation that serves as a pass-through
between frontend and backend stages.
"""

import pytest
from gelb.gelb_ast.ASTNodes import Program_N, IntLiteral_N
from gelb.midware.stage2_midware import (
    validate_midware_input,
    fold_constants
)
from gelb.tests.test_utils import get_typed_ast
from gelb.tests.unit.midware.midware_test_utils import (
    get_midware_processed_ast,
    create_simple_test_program,
    assert_midware_preserves_structure,
    assert_midware_transformations_applied
)


class TestMidwarePassThrough:
    """Test the basic pass-through functionality of the midware stage."""
    
    def test_fold_constants_with_valid_program(self):
        """Test that fold_constants handles a valid Program_N correctly."""
        gelb_code = create_simple_test_program()
        original_ast = get_typed_ast(gelb_code)
        
        # Process through midware stages
        validate_midware_input(original_ast)
        processed_ast = fold_constants(original_ast)
        
        # Should preserve structure
        assert_midware_preserves_structure(original_ast, processed_ast)
    
    def test_validate_midware_input_rejects_non_program_node(self):
        """Test that validate_midware_input rejects non-Program_N nodes."""
        # Create a non-Program_N node
        invalid_ast = IntLiteral_N(code_range=None, value=42)
        
        with pytest.raises(TypeError) as excinfo:
            validate_midware_input(invalid_ast)
        
        assert "Expected Program_N, got IntLiteral_N" in str(excinfo.value)
    
    def test_validate_midware_input_with_valid_program(self):
        """Test input validation with a valid Program_N."""
        gelb_code = create_simple_test_program()
        ast = get_typed_ast(gelb_code)
        
        # Should not raise any exceptions
        validate_midware_input(ast)
    
    def test_validate_midware_input_rejects_wrong_type(self):
        """Test that input validation rejects non-Program_N types."""
        invalid_ast = IntLiteral_N(code_range=None, value=42)
        
        with pytest.raises(TypeError) as excinfo:
            validate_midware_input(invalid_ast)
        
        assert "Expected Program_N, got IntLiteral_N" in str(excinfo.value)
    
    def test_constant_folding_works(self):
        """Test that constant folding optimization works correctly."""
        gelb_code = create_simple_test_program()
        ast = get_typed_ast(gelb_code)
        
        # Apply constant folding
        folded_ast = fold_constants(ast)
        
        # Should return a valid AST
        assert isinstance(folded_ast, Program_N)
    
    def test_full_midware_pipeline(self):
        """Test the complete midware processing pipeline."""
        gelb_code = create_simple_test_program()
        
        # Get AST processed through complete pipeline
        processed_ast = get_midware_processed_ast(gelb_code)
        
        # Verify it's still a valid Program_N
        assert isinstance(processed_ast, Program_N)
        
        # Verify structure is preserved
        original_ast = get_typed_ast(gelb_code)
        assert_midware_transformations_applied(original_ast, processed_ast)


class TestMidwareWithComplexPrograms:
    """Test midware with more complex GeLB programs."""
    
    def test_program_with_multiple_blocks(self):
        """Test midware with a program containing multiple initializer/dynamic/gauge blocks."""
        gelb_code = '''
        simulation_description("Test multiple blocks");
        
        global_constants {
            const int N = 32;
            const real TAU = 0.6;
        }
        
        lattices {
            lattice f(1, 1, int, N, false);
            lattice g(1, 1, real, N, false);
        }
        
        initializer Init1 {
            f.out[x | 0] = 0;
        }
        
        initializer Init2 {
            g.out[x | 0] = 0.0;
        }
        
        dynamic Update1 {
            f.out[x | 0] = 1;
        }
        
        dynamic Update2 {
            g.out[x | 0] = TAU;
        }
        
        gauge Output1(out = {int state;}) {
            state = f.in[x | 0];
        }
        
        gauge Output2(out = {real value;}) {
            value = g.in[x | 0];
        }
        
        node_classes {
            node_class BULK(Init1, Update1, Output1);
            node_class SPECIAL(Init2, Update2, Output2);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        '''
        
        # Should process without errors
        processed_ast = get_midware_processed_ast(gelb_code)
        
        # Verify structure
        assert isinstance(processed_ast, Program_N)
        assert len(processed_ast.initializers) == 2
        assert len(processed_ast.dynamics) == 2
        assert len(processed_ast.gauges) == 2
    
    def test_program_with_constants_and_expressions(self):
        """Test midware with a program containing complex constant expressions."""
        gelb_code = '''
        simulation_description("Test constants and expressions");
        
        global_constants {
            const int N = 16;
            const int M = N * 2;
            const real PI = 3.14159;
        }
        
        lattices {
            lattice f(1, 1, real, M, true);
        }
        
        initializer Init {
            f.out[x | 0] = PI * 2.0;
        }
        
        dynamic Update {
            f.out[x | 0] = f.in[x | 0] + 1.0;
        }
        
        gauge Output(out = {real result;}) {
            result = f.in[x | 0] / PI;
        }
        
        node_classes {
            node_class BULK(Init, Update, Output);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        '''
        
        # Should process without errors
        processed_ast = get_midware_processed_ast(gelb_code)
        
        # Verify structure is preserved
        assert isinstance(processed_ast, Program_N)
        original_ast = get_typed_ast(gelb_code)
        assert_midware_preserves_structure(original_ast, processed_ast)