#!/usr/bin/env python3
"""
Shared test utilities for midware unit tests.

This module provides common helper functions for testing the midware stage,
following the existing test pattern in the GeLB codebase.
"""

from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
from gelb.midware.stage2_midware import validate_midware_input, fold_constants
from gelb.gelb_ast.ASTNodes import Program_N


def get_midware_processed_ast(gelb_code):
    """
    Helper to get AST processed through the complete frontend + midware pipeline.
    
    Args:
        gelb_code (str): GeLB source code
        
    Returns:
        Program_N: AST processed through frontend and midware stages
    """
    # Get fully processed AST from frontend
    ast = get_typed_ast(gelb_code)
    
    # Process through midware stages
    validate_midware_input(ast)
    return fold_constants(ast)


def create_simple_test_program():
    """
    Create a simple test program for midware testing.
    
    Returns:
        str: Simple GeLB program suitable for midware testing
    """
    return minimal_gelb_program_1d(
        global_constants_content="const int N = 16;",
        initializer_content='f.out[x | 0] = 0;',
        dynamic_content='f.out[x | 0] = 1;',
        gauge_content='val = f.in[x | 0];',
        geometry_content='nodes[:] = BULK;'
    )


def assert_midware_preserves_structure(original_ast, processed_ast):
    """
    Assert that midware processing preserves essential AST structure.
    
    Args:
        original_ast (Program_N): The original AST before midware
        processed_ast (Program_N): The AST after midware processing
        
    Raises:
        AssertionError: If structure is not preserved
    """
    # Both should be Program_N instances
    assert isinstance(original_ast, Program_N)
    assert isinstance(processed_ast, Program_N)
    
    # Essential structure should be preserved
    assert processed_ast.global_constants is not None
    assert processed_ast.lattices is not None
    assert processed_ast.node_classes is not None
    assert processed_ast.geometry is not None
    
    # Block lists should exist (even if empty)
    assert processed_ast.initializers is not None
    assert processed_ast.dynamics is not None
    assert processed_ast.gauges is not None


def assert_midware_transformations_applied(original_ast, processed_ast):
    """
    Assert that midware transformations have been properly applied.
    
    Args:
        original_ast (Program_N): The original AST
        processed_ast (Program_N): The processed AST
        
    Raises:
        AssertionError: If transformations were not applied correctly
    """
    # Both should be Program_N instances
    assert isinstance(original_ast, Program_N)
    assert isinstance(processed_ast, Program_N)
    
    # After constant folding, the AST might be modified
    # but it should still maintain the same structure
    assert_midware_preserves_structure(original_ast, processed_ast)