#!/usr/bin/env python3

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
from gelb.utils.exceptions import GeLBExTypeError


class TestLatticeConstantValidation:
    """Test lattice parameter validation with global constants."""
    
    def test_negative_constant_grid_size_invalid(self):
        """Test that negative constant grid_size values are rejected."""
        gelb_code = """
            simulation_description("Test negative constant grid_size");
            
            global_constants {
                const int N = -32;
            }
            
            lattices {
                lattice f(1, 1, int, N, false);
            }
            
            initializer Init { f.out[x | 0] = 0; }
            dynamic Dyn { f.out[x | 0] = 1; }
            gauge Out -> (int val) { val = f.in[x | 0]; }
            node_classes { node_class BULK(Init, Dyn, Out); }
            geometry { nodes[:] = BULK; }
        """
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Grid size -32 is invalid" in error_msg
        assert "Grid size must be positive" in error_msg
    
    def test_negative_constant_d_invalid(self):
        """Test that negative constant d values are rejected."""
        gelb_code = """
            simulation_description("Test negative constant d");
            
            global_constants {
                const int D = -1;
            }
            
            lattices {
                lattice f(D, 1, int, 32, false);
            }
            
            initializer Init { f.out[x | 0] = 0; }
            dynamic Dyn { f.out[x | 0] = 1; }
            gauge Out -> (int val) { val = f.in[x | 0]; }
            node_classes { node_class BULK(Init, Dyn, Out); }
            geometry { nodes[:] = BULK; }
        """
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Lattice dimensionality d=-1 is invalid" in error_msg
        assert "Dimensionality must be between 1 and 3" in error_msg
    
    def test_negative_constant_q_invalid(self):
        """Test that negative constant q values are rejected."""
        gelb_code = """
            simulation_description("Test negative constant q");
            
            global_constants {
                const int Q = -5;
            }
            
            lattices {
                lattice f(1, Q, int, 32, false);
            }
            
            initializer Init { f.out[x | 0] = 0; }
            dynamic Dyn { f.out[x | 0] = 1; }
            gauge Out -> (int val) { val = f.in[x | 0]; }
            node_classes { node_class BULK(Init, Dyn, Out); }
            geometry { nodes[:] = BULK; }
        """
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Number of distribution functions q=-5 is invalid" in error_msg
        assert "Number of distribution functions must be positive" in error_msg
    
    def test_array_constant_with_shape_mismatch_invalid(self):
        """Test that array constants with wrong shape for d are rejected."""
        gelb_code = """
            simulation_description("Test array constant shape mismatch");
            
            global_constants {
                const int GRID = {32, 64};
            }
            
            lattices {
                lattice f(1, 1, int, GRID, false);
            }
            
            initializer Init { f.out[x | 0] = 0; }
            dynamic Dyn { f.out[x | 0] = 1; }
            gauge Out -> (int val) { val = f.in[x | 0]; }
            node_classes { node_class BULK(Init, Dyn, Out); }
            geometry { nodes[:] = BULK; }
        """
        
        # Note: This will fail at constant declaration stage due to type mismatch
        # (scalar int vs array int), not at lattice validation stage
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(gelb_code)
    
    def test_array_constant_with_negative_elements_invalid(self):
        """Test that array constants with negative elements are rejected."""
        gelb_code = """
            simulation_description("Test array constant with negative elements");
            
            global_constants {
                const int GRID = {32, -64, 128};
            }
            
            lattices {
                lattice f(3, 27, int, GRID, {false, true, false});
            }
            
            initializer Init { f.out[x | 0] = 0; }
            dynamic Dyn { f.out[x | 0] = 1; }
            gauge Out -> (int val) { val = f.in[x | 0]; }
            node_classes { node_class BULK(Init, Dyn, Out); }
            geometry { nodes[:] = BULK; }
        """
        
        # Note: This will also fail at constant declaration stage due to type system
        # but shows the pattern we want to handle
        with pytest.raises(GeLBExTypeError):
            get_typed_ast(gelb_code)
    
    def test_positive_constants_valid(self):
        """Test that positive constant values are accepted."""
        gelb_code = """
            simulation_description("Test positive constants");
            
            global_constants {
                const int D = 2;
                const int Q = 9;
                const int N = 64;
            }
            
            lattices {
                lattice f(D, Q, int, {N, N}, {false, true});
            }
            
            initializer Init { f.out[x, y | 0] = 0; }
            dynamic Dyn { f.out[x, y | 0] = 1; }
            gauge Out -> (int val) { val = f.in[x, y | 0]; }
            node_classes { node_class BULK(Init, Dyn, Out); }
            geometry { nodes[:, :] = BULK; }
        """
        
        # Should compile successfully
        ast = get_typed_ast(gelb_code)
        assert isinstance(ast, Program_N)
    
    def test_expression_constants_invalid(self):
        """Test that constants defined by expressions are properly validated."""
        gelb_code = """
            simulation_description("Test expression constants");
            
            global_constants {
                const int BASE = 16;
                const int NEGATIVE = BASE - 20;  // Results in -4
            }
            
            lattices {
                lattice f(1, 1, int, NEGATIVE, false);
            }
            
            initializer Init { f.out[x | 0] = 0; }
            dynamic Dyn { f.out[x | 0] = 1; }
            gauge Out -> (int val) { val = f.in[x | 0]; }
            node_classes { node_class BULK(Init, Dyn, Out); }
            geometry { nodes[:] = BULK; }
        """
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Grid size -4 is invalid" in error_msg
        assert "Grid size must be positive" in error_msg
    
    def test_zero_constant_q_invalid(self):
        """Test that zero constant q values are rejected."""
        gelb_code = """
            simulation_description("Test zero constant q");
            
            global_constants {
                const int Q_VAL = 0;
            }
            
            lattices {
                lattice f(1, Q_VAL, int, 32, false);
            }
            
            initializer Init { f.out[x | 0] = 0; }
            dynamic Dyn { f.out[x | 0] = 1; }
            gauge Out -> (int val) { val = f.in[x | 0]; }
            node_classes { node_class BULK(Init, Dyn, Out); }
            geometry { nodes[:] = BULK; }
        """
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Number of distribution functions q=0 is invalid" in error_msg
        assert "Number of distribution functions must be positive" in error_msg


class TestConstantValidationTiming:
    """Test that validation happens at the right time in the pipeline."""
    
    def test_validation_happens_after_constant_resolution(self):
        """Test that validation sees resolved constant values, not identifiers."""
        gelb_code = """
            simulation_description("Test validation timing");
            
            global_constants {
                const int BAD_D = 5;  // > 3, should be caught
            }
            
            lattices {
                lattice f(BAD_D, 1, int, 32, false);
            }
            
            initializer Init { f.out[x | 0] = 0; }
            dynamic Dyn { f.out[x | 0] = 1; }
            gauge Out -> (int val) { val = f.in[x | 0]; }
            node_classes { node_class BULK(Init, Dyn, Out); }
            geometry { nodes[:] = BULK; }
        """
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_typed_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        # Should show resolved value (5), not identifier name (BAD_D)
        assert "Lattice dimensionality d=5 is invalid" in error_msg
        assert "Dimensionality must be between 1 and 3" in error_msg
    
    def test_unresolved_identifiers_skip_validation(self):
        """Test that if constants aren't resolved, validation is skipped gracefully."""
        # This test verifies that validation doesn't crash on unresolved identifiers
        # In practice, this shouldn't happen in normal compilation, but it's good to be defensive
        
        gelb_code = """
            simulation_description("Test unresolved identifiers");
            
            lattices {
                lattice f(UNKNOWN_D, 1, int, 32, false);
            }
            
            initializer Init { f.out[x | 0] = 0; }
            dynamic Dyn { f.out[x | 0] = 1; }
            gauge Out -> (int val) { val = f.in[x | 0]; }
            node_classes { node_class BULK(Init, Dyn, Out); }
            geometry { nodes[:] = BULK; }
        """
        
        # Should fail at symbol resolution stage, not lattice validation
        with pytest.raises(Exception):  # Will be a symbol resolution error
            get_typed_ast(gelb_code)