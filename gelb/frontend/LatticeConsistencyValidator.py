#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBException


class LatticeConsistencyValidationError(GeLBException):
    """Exception raised when lattices have inconsistent grid properties."""
    def __init__(self, message, code_range=None):
        super().__init__(message, code_range)


class LatticeConsistencyValidator(ASTBaseVisitor):
    """
    Validates that all lattices have identical grid_size and periodicity.
    
    This is a GeLB v1 restriction: all lattices must have the same grid dimensions
    and periodicity settings. This validator ensures this constraint is enforced
    during compilation.
    """
    
    def visitProgram_N(self, node: Program_N, ast_root_node: Program_N):
        """
        Main entry point to validate lattice consistency across the program.
        """
        if node.lattices is not None:
            self.visit(node.lattices, ast_root_node)
        return node
    
    def visitLatticesBlock_N(self, node: LatticesBlock_N, ast_root_node: Program_N):
        """
        Validate that all lattices in the block have identical grid properties.
        """
        if not node.stmts or len(node.stmts.elements) <= 1:
            # Nothing to validate if there's 0 or 1 lattice
            return node
        
        # Get the first lattice as reference
        first_lattice = node.stmts.elements[0]
        
        # Check all subsequent lattices against the first
        for i, lattice in enumerate(node.stmts.elements[1:], start=1):
            # Check grid_size consistency
            if not self._grid_sizes_equal(first_lattice.grid_size, lattice.grid_size):
                raise LatticeConsistencyValidationError(
                    f"Lattice '{lattice.name}' has different grid_size than lattice '{first_lattice.name}'. "
                    f"All lattices must have identical grid dimensions in GeLB v1.",
                    lattice.code_range
                )
            
            # Check periodicity consistency
            if not self._periodicities_equal(first_lattice.periodicity, lattice.periodicity):
                raise LatticeConsistencyValidationError(
                    f"Lattice '{lattice.name}' has different periodicity than lattice '{first_lattice.name}'. "
                    f"All lattices must have identical periodicity settings in GeLB v1.",
                    lattice.code_range
                )
        
        return node
    
    def _grid_sizes_equal(self, grid_size1, grid_size2):
        """
        Check if two grid_size expressions are equal.
        
        This handles various AST node types:
        - IntLiteral_N for 1D cases
        - Array1DLiteral_N for multi-dimensional cases
        - Identifier_N for references to constants
        - Other expression types
        """
        # If they're the same object, they're equal
        if grid_size1 is grid_size2:
            return True
        
        # Check if both are None
        if grid_size1 is None or grid_size2 is None:
            return grid_size1 == grid_size2
        
        # Compare by type
        if type(grid_size1) != type(grid_size2):
            return False
        
        # Handle IntLiteral_N (1D case)
        if isinstance(grid_size1, IntLiteral_N):
            return grid_size1.value == grid_size2.value
        
        # Handle Array1DLiteral_N (multi-dimensional case)
        if isinstance(grid_size1, Array1DLiteral_N):
            elements1 = grid_size1.value.elements
            elements2 = grid_size2.value.elements
            
            if len(elements1) != len(elements2):
                return False
            
            # Recursively compare each element
            for elem1, elem2 in zip(elements1, elements2):
                if not self._grid_sizes_equal(elem1, elem2):
                    return False
            return True
        
        # Handle Identifier_N (constant references)
        if isinstance(grid_size1, Identifier_N):
            return grid_size1.name == grid_size2.name
        
        # For other expression types, convert to string and compare
        # This is a simple heuristic that may need refinement
        return str(grid_size1) == str(grid_size2)
    
    def _periodicities_equal(self, periodicity1, periodicity2):
        """
        Check if two periodicity expressions are equal.
        
        This handles:
        - BoolLiteral_N for simple true/false
        - Array1DLiteral_N for per-dimension periodicity
        - Identifier_N for references to constants
        - Other expression types
        """
        # If they're the same object, they're equal
        if periodicity1 is periodicity2:
            return True
        
        # Check if both are None
        if periodicity1 is None or periodicity2 is None:
            return periodicity1 == periodicity2
        
        # Compare by type
        if type(periodicity1) != type(periodicity2):
            return False
        
        # Handle BoolLiteral_N
        if isinstance(periodicity1, BoolLiteral_N):
            return periodicity1.value == periodicity2.value
        
        # Handle Array1DLiteral_N (per-dimension periodicity)
        if isinstance(periodicity1, Array1DLiteral_N):
            elements1 = periodicity1.value.elements
            elements2 = periodicity2.value.elements
            
            if len(elements1) != len(elements2):
                return False
            
            # Recursively compare each element
            for elem1, elem2 in zip(elements1, elements2):
                if not self._periodicities_equal(elem1, elem2):
                    return False
            return True
        
        # Handle Identifier_N (constant references)
        if isinstance(periodicity1, Identifier_N):
            return periodicity1.name == periodicity2.name
        
        # For other expression types, convert to string and compare
        return str(periodicity1) == str(periodicity2)