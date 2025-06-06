#!/usr/bin/env python3

"""
GeLB Midware Stage 2 - AST Transformations and Optimizations

This module handles the middle stage of the GeLB compilation pipeline,
between the frontend (stage 1) and backend (stage 3).

Implements optimization passes including:
- Constant folding
- Future: Dead code elimination, common subexpression elimination
"""

from gelb.gelb_ast.ASTNodes import Program_N
from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor


def process_ast(ast):
    """
    Process the AST through the midware stage.
    
    Applies optimization passes in the correct order:
    1. Constant folding - evaluates constant expressions
    2. Future optimizations - dead code elimination, etc.
    
    Args:
        ast (Program_N): The AST from frontend stage 1
        
    Returns:
        Program_N: The processed AST with optimizations applied
        
    Raises:
        TypeError: If ast is not a Program_N instance
    """
    if not isinstance(ast, Program_N):
        raise TypeError(
            f"Midware expects a Program_N AST root, but got {type(ast).__name__}. "
            "Ensure the frontend properly validates the AST root."
        )
    
    validate_midware_input(ast)
    
    # Apply constant folding optimization
    ast = apply_constant_folding(ast)
    
    # Apply other optimizations
    ast = apply_optimizations(ast)
    
    # Apply transformations for backend compatibility
    ast = apply_transformations(ast)
    
    return ast


def validate_midware_input(ast):
    """
    Validate that the AST is ready for midware processing.
    
    Args:
        ast (Program_N): The AST to validate
        
    Raises:
        TypeError: If ast is not the expected type
        AttributeError: If required AST attributes are missing
    """
    if not isinstance(ast, Program_N):
        raise TypeError(f"Expected Program_N, got {type(ast).__name__}")
    
    # Check that essential attributes exist
    required_attrs = [
        'global_constants', 'lattices', 'initializers', 
        'dynamics', 'gauges', 'node_classes', 'geometry'
    ]
    
    for attr in required_attrs:
        if not hasattr(ast, attr):
            raise AttributeError(f"AST missing required attribute: {attr}")


def apply_constant_folding(ast):
    """
    Apply constant folding optimization to the AST.
    
    Evaluates constant expressions at compile time and replaces them
    with their computed literal values.
    
    Args:
        ast (Program_N): The AST to optimize
        
    Returns:
        Program_N: The AST with constant expressions folded
    """
    folder = ConstantFoldingVisitor()
    return folder.visit(ast, ast)


def apply_optimizations(ast):
    """
    Apply additional optimization passes to the AST.
    
    Currently empty - future optimizations will be added here.
    
    Args:
        ast (Program_N): The AST to optimize
        
    Returns:
        Program_N: The optimized AST
    """
    # Future: implement additional optimization passes here
    # Examples:
    # - Dead code elimination  
    # - Common subexpression elimination
    # - Loop optimizations
    
    return ast


def apply_transformations(ast):
    """
    Apply necessary AST transformations for backend compatibility.
    
    Currently empty for MVP implementation.
    
    Args:
        ast (Program_N): The AST to transform
        
    Returns:
        Program_N: The transformed AST
    """
    # Future: implement transformations here
    # Examples:
    # - Expand compact notations
    # - Normalize lattice operations
    # - Prepare for code generation
    
    return ast