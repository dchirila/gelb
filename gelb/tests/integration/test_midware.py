#!/usr/bin/env python3
"""
Integration tests for the midware stage.

Tests the midware stage in the context of the full compilation pipeline,
ensuring it integrates correctly with frontend and prepares for backend.
"""

import pytest
from gelb.frontend.stage1_frontend import (
    get_ast,
    validate_ast_root_is_program,
    build_symbols_tables,
    add_implicit_symbols,
    resolve_all_constants,
    resolve_ranges,
    infer_types,
    validate_constant_assignments
)
from gelb.midware.stage2_midware import validate_midware_input, fold_constants
from gelb.gelb_ast.ASTNodes import Program_N
from gelb.tests.test_utils import minimal_gelb_program_1d


class TestMidwareIntegration:
    """Integration tests for midware in the compilation pipeline."""
    
    def test_frontend_to_midware_pipeline(self):
        """Test that midware integrates correctly with frontend output."""
        gelb_code = minimal_gelb_program_1d(
            global_constants_content="const int N = 32;",
            initializer_content='f.out[x | 0] = 0;',
            dynamic_content='f.out[x | 0] = 1;',
            gauge_content='val = f.in[x | 0];',
            geometry_content='nodes[:] = BULK;'
        )
        
        # Complete frontend pipeline
        ast = get_ast("gelb_program", gelb_code)
        validate_ast_root_is_program(ast)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = validate_constant_assignments(ast)
        
        # Process through midware
        validate_midware_input(ast)
        processed_ast = fold_constants(ast)
        
        # Verify output is suitable for backend
        assert isinstance(processed_ast, Program_N)
        assert processed_ast.global_constants is not None
        assert processed_ast.lattices is not None
        assert processed_ast.node_classes is not None
        assert processed_ast.geometry is not None
    
    def test_midware_with_ex0_example_structure(self):
        """Test midware with a structure similar to ex0_int_vec_setto_one.gelb."""
        gelb_code = '''
        simulation_description("Pretty much the hello world of GeLB");

        lattices {
          lattice f(1, 1, int, 32, false);
        }

        initializer SetDFsToZero {
          f.out[x | 0] = 0;
        }

        dynamic SetDFsToOne {
          f.out[x | 0] = 1;
        }

        gauge CurrentState(out = {int state;}) {
          state = f.in[x | 0];
        }

        node_classes {
          node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);
        }

        geometry {
          nodes[:] = BULK;
        }
        '''
        
        # Complete frontend pipeline
        ast = get_ast("gelb_program", gelb_code)
        validate_ast_root_is_program(ast)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = validate_constant_assignments(ast)
        
        # Process through midware
        validate_midware_input(ast)
        processed_ast = fold_constants(ast)
        
        # Verify key structures for backend
        assert isinstance(processed_ast, Program_N)
        
        # Should have lattice definition
        assert processed_ast.lattices is not None
        assert len(processed_ast.lattices.stmts) == 1
        
        # Should have one of each block type
        assert len(processed_ast.initializers) == 1
        assert len(processed_ast.dynamics) == 1
        assert len(processed_ast.gauges) == 1
        
        # Should have node class definition
        assert processed_ast.node_classes is not None
        assert len(processed_ast.node_classes.stmts) == 1
        
        # Should have geometry setup
        assert processed_ast.geometry is not None
    
    def test_midware_preserves_type_information(self):
        """Test that midware preserves type inference information."""
        gelb_code = '''
        simulation_description("Test type preservation");
        
        global_constants {
            const int N = 16;
            const real PI = 3.14;
        }
        
        lattices {
            lattice f(1, 1, real, N, true);
        }
        
        initializer Init {
            f.out[x | 0] = PI;
        }
        
        dynamic Update {
            f.out[x | 0] = f.in[x | 0] + 1.0;
        }
        
        gauge Output(out = {real value;}) {
            value = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(Init, Update, Output);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        '''
        
        # Complete frontend pipeline with type inference
        ast = get_ast("gelb_program", gelb_code)
        validate_ast_root_is_program(ast)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = validate_constant_assignments(ast)
        
        # Verify type information exists before midware
        initializer_stmt = ast.initializers[0].stmts[0]
        assert hasattr(initializer_stmt.rhs, 'inferred_type')
        
        # Process through midware
        validate_midware_input(ast)
        processed_ast = fold_constants(ast)
        
        # Verify type information is preserved
        processed_initializer_stmt = processed_ast.initializers[0].stmts[0]
        assert hasattr(processed_initializer_stmt.rhs, 'inferred_type')
        
        # For pass-through, should be the same object
        assert processed_initializer_stmt is initializer_stmt
    
    def test_midware_error_handling(self):
        """Test that midware properly handles invalid input."""
        # Test with non-Program_N input
        from gelb.gelb_ast.ASTNodes import IntLiteral_N
        invalid_ast = IntLiteral_N(code_range=None, value=42)
        
        with pytest.raises(TypeError) as excinfo:
            validate_midware_input(invalid_ast)
        
        assert "Expected Program_N, got IntLiteral_N" in str(excinfo.value)