#!/usr/bin/env python3

"""
GeLB Midware Stage 2 - AST Transformations and Optimizations

This module provides individual midware stage functions that can be called
explicitly from the main compiler driver. Each function represents a specific
optimization or transformation pass.

Functions are organized in the order they should be applied:
1. validate_midware_input() - Input validation
2. fold_constants() - Constant folding optimization
3. Future: dead code elimination, common subexpression elimination, etc.
"""

from gelb.gelb_ast.ASTNodes import Program_N
from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
from gelb.midware.DivisionByZeroValidator import DivisionByZeroValidator


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


def fold_constants(ast):
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


def validate_division_by_zero(ast):
    """
    Check for division by zero operations in the AST.
    
    Must run AFTER constant folding and propagation to catch all
    compile-time detectable division by zero errors, including:
    - Direct literals: 1 / 0
    - Constants: const int ZERO = 0; ... 1 / ZERO
    - Expressions: const int ZERO = 1 - 1; ... 1 / ZERO
    
    Args:
        ast (Program_N): The AST to validate
        
    Returns:
        Program_N: The validated AST
        
    Raises:
        GeLBExTypeError: If division by zero is detected
    """
    validator = DivisionByZeroValidator()
    return validator.visit(ast, ast)


# Future midware stage functions:

def eliminate_dead_code(ast):
    """
    Remove unreachable code and unused definitions from the AST.
    
    Args:
        ast (Program_N): The AST to optimize
        
    Returns:
        Program_N: The AST with dead code eliminated
    """
    # TODO: Implement dead code elimination
    # Examples:
    # - Remove unused constant definitions
    # - Remove unreferenced symbols
    # - Optimize away redundant calculations
    return ast


def eliminate_common_subexpressions(ast):
    """
    Identify and reuse common subexpressions.
    
    Args:
        ast (Program_N): The AST to optimize
        
    Returns:
        Program_N: The AST with common subexpressions eliminated
    """
    # TODO: Implement common subexpression elimination
    return ast


def optimize_lattice_access_patterns(ast):
    """
    Optimize lattice access patterns for better memory locality.
    
    Args:
        ast (Program_N): The AST to optimize
        
    Returns:
        Program_N: The AST with optimized lattice access patterns
    """
    # TODO: Implement lattice access pattern optimizations
    return ast


def prepare_for_backend(ast):
    """
    Apply necessary AST transformations for backend compatibility.
    
    Args:
        ast (Program_N): The AST to transform
        
    Returns:
        Program_N: The transformed AST ready for backend processing
    """
    # TODO: Implement backend preparation transformations
    # Examples:
    # - Expand compact notations
    # - Normalize lattice operations
    # - Add backend-specific annotations
    return ast