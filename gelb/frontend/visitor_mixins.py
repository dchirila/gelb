#!/usr/bin/env python3

"""
Shared mixins for visitor classes to reduce code duplication.

This module contains common patterns and helper methods that are used across
multiple visitor classes in the frontend.
"""

from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import *


class BinaryOperationMixin:
    """
    Mixin providing standardized binary operation handling for visitors.
    
    This mixin can be used by any visitor that needs to process binary operations
    with consistent patterns. It provides a mapping-based approach to handle
    different operation types.
    """
    
    # Mapping of binary operation nodes to their operation types
    BINARY_OPERATION_TYPES = {
        'Add_N': 'arithmetic',
        'Sub_N': 'arithmetic', 
        'Mul_N': 'arithmetic',
        'Div_N': 'arithmetic',
        'Pow_N': 'arithmetic',
        'Less_N': 'comparison',
        'Greater_N': 'comparison',
        'LessEqual_N': 'comparison',
        'GreaterEqual_N': 'comparison',
        'Equal_N': 'comparison',
        'NotEqual_N': 'comparison',
        'And_N': 'logical',
        'Or_N': 'logical'
    }
    
    def visitAdd_N(self, node, ast_root_node):
        """Infer type of addition operation."""
        return self._handle_binary_operation(node, ast_root_node, "arithmetic")
    
    def visitSub_N(self, node, ast_root_node):
        """Infer type of subtraction operation."""
        return self._handle_binary_operation(node, ast_root_node, "arithmetic")
    
    def visitMul_N(self, node, ast_root_node):
        """Infer type of multiplication operation."""
        return self._handle_binary_operation(node, ast_root_node, "arithmetic")
    
    def visitDiv_N(self, node, ast_root_node):
        """Infer type of division operation."""
        return self._handle_binary_operation(node, ast_root_node, "arithmetic")
    
    def visitPow_N(self, node, ast_root_node):
        """Infer type of power operation."""
        return self._handle_binary_operation(node, ast_root_node, "arithmetic")
    
    def visitLess_N(self, node, ast_root_node):
        """Comparison operations always return bool."""
        return self._handle_binary_operation(node, ast_root_node, "comparison")
    
    def visitGreater_N(self, node, ast_root_node):
        """Comparison operations always return bool."""
        return self._handle_binary_operation(node, ast_root_node, "comparison")
    
    def visitLessEqual_N(self, node, ast_root_node):
        """Comparison operations always return bool."""
        return self._handle_binary_operation(node, ast_root_node, "comparison")
    
    def visitGreaterEqual_N(self, node, ast_root_node):
        """Comparison operations always return bool."""
        return self._handle_binary_operation(node, ast_root_node, "comparison")
    
    def visitEqual_N(self, node, ast_root_node):
        """Comparison operations always return bool."""
        return self._handle_binary_operation(node, ast_root_node, "comparison")
    
    def visitNotEqual_N(self, node, ast_root_node):
        """Comparison operations always return bool."""
        return self._handle_binary_operation(node, ast_root_node, "comparison")
    
    def visitAnd_N(self, node, ast_root_node):
        """Logical operations require bool operands and return bool."""
        return self._handle_binary_operation(node, ast_root_node, "logical")
    
    def visitOr_N(self, node, ast_root_node):
        """Logical operations require bool operands and return bool."""
        return self._handle_binary_operation(node, ast_root_node, "logical")
    
    def _handle_binary_operation(self, node, ast_root_node, operation_type):
        """
        Override this method in the concrete visitor to handle binary operations.
        
        Args:
            node: The binary operation AST node
            ast_root_node: The root Program_N node
            operation_type: String indicating operation type ('arithmetic', 'comparison', 'logical')
            
        Returns:
            The processed node
        """
        raise NotImplementedError("Subclasses must implement _handle_binary_operation")


class ArrayLiteralProcessingMixin:
    """
    Mixin providing standardized array literal processing for visitors.
    
    This reduces the duplication in processing 1D, 2D, 3D, and 4D array literals
    by providing a generic processing method.
    """
    
    def _process_array_literal(self, node, ast_root_node, dimensions):
        """
        Generic array literal processing method.
        
        Args:
            node: Array literal AST node (Array1DLiteral_N, Array2DLiteral_N, etc.)
            ast_root_node: The root Program_N node
            dimensions: Number of dimensions (1, 2, 3, or 4)
            
        Returns:
            The processed node
        """
        if not node.value.elements:
            raise GeLBExTypeError(
                node,
                "Array literal cannot be empty",
                "Array literals must contain at least one element. Use: [1, 2, 3] instead of []"
            )
        
        # Process all elements recursively
        self._visit_array_elements_recursively(node.value.elements, ast_root_node, dimensions)
        
        # Let the concrete visitor handle dimension-specific processing
        return self._handle_array_literal_dimensions(node, ast_root_node, dimensions)
    
    def _visit_array_elements_recursively(self, elements, ast_root_node, remaining_dims):
        """Recursively visit array elements at all nesting levels."""
        for elem in elements:
            if remaining_dims > 1:
                # Still have nested structure to traverse
                self._visit_array_elements_recursively(elem.value.elements, ast_root_node, remaining_dims - 1)
            else:
                # At the leaf level, visit the element
                self.visit(elem, ast_root_node)
    
    def _handle_array_literal_dimensions(self, node, ast_root_node, dimensions):
        """
        Override this method in the concrete visitor to handle dimension-specific logic.
        
        Args:
            node: The array literal AST node
            ast_root_node: The root Program_N node  
            dimensions: Number of dimensions
            
        Returns:
            The processed node
        """
        raise NotImplementedError("Subclasses must implement _handle_array_literal_dimensions")


class ProgramTraversalMixin:
    """
    Mixin providing standardized program traversal patterns.
    
    This eliminates the duplication in visitProgram_N methods across different visitors.
    """
    
    def traverse_program_blocks(self, node: Program_N, ast_root_node: Program_N):
        """
        Standard program traversal that visits all blocks in the correct order.
        
        This method handles the common pattern of visiting all blocks in a program
        while allowing individual visitors to customize the processing through hooks.
        
        Args:
            node: The Program_N node to traverse
            ast_root_node: The root Program_N node
        """
        # Store global constants for cross-block access
        if hasattr(self, '_store_global_constants'):
            self._store_global_constants(node)
        
        # Process global constants first
        if node.global_constants is not None:
            self._before_block_visit(node.global_constants, 'global_constants')
            if hasattr(self, 'visitGlobalConstantsBlock_N'):
                self.visit(node.global_constants, ast_root_node)
            self._after_block_visit(node.global_constants, 'global_constants')
        
        # Process lattices block
        if node.lattices is not None:
            self._before_block_visit(node.lattices, 'lattices')
            if hasattr(self, 'visitLatticesBlock_N'):
                self.visit(node.lattices, ast_root_node)
            self._after_block_visit(node.lattices, 'lattices')
        
        # Process initializer blocks
        if node.initializers is not None:
            for initializer in node.initializers:
                self._before_block_visit(initializer, 'initializer')
                if hasattr(self, 'visitInitializerBlock_N'):
                    self.visit(initializer, ast_root_node)
                self._after_block_visit(initializer, 'initializer')
        
        # Process dynamic blocks
        if node.dynamics is not None:
            for dynamic in node.dynamics:
                self._before_block_visit(dynamic, 'dynamic')
                if hasattr(self, 'visitDynamicBlock_N'):
                    self.visit(dynamic, ast_root_node)
                self._after_block_visit(dynamic, 'dynamic')
        
        # Process gauge blocks
        if node.gauges is not None:
            for gauge in node.gauges:
                self._before_block_visit(gauge, 'gauge')
                if hasattr(self, 'visitGaugeBlock_N'):
                    self.visit(gauge, ast_root_node)
                self._after_block_visit(gauge, 'gauge')
        
        # Process node classes
        if node.node_classes is not None:
            self._before_block_visit(node.node_classes, 'node_classes')
            if hasattr(self, 'visitNodeClassesBlock_N'):
                self.visit(node.node_classes, ast_root_node)
            self._after_block_visit(node.node_classes, 'node_classes')
        
        # Process geometry
        if node.geometry is not None:
            self._before_block_visit(node.geometry, 'geometry')
            if hasattr(self, 'visitGeometryBlock_N'):
                self.visit(node.geometry, ast_root_node)
            self._after_block_visit(node.geometry, 'geometry')
    
    def _before_block_visit(self, block_node, block_type):
        """
        Hook called before visiting each block. Override to customize behavior.
        
        Args:
            block_node: The block AST node about to be visited
            block_type: String identifying the block type
        """
        pass
    
    def _after_block_visit(self, block_node, block_type):
        """
        Hook called after visiting each block. Override to customize behavior.
        
        Args:
            block_node: The block AST node that was just visited
            block_type: String identifying the block type
        """
        pass


class SymbolTableUtilityMixin:
    """
    Mixin providing standardized symbol table operations.
    
    This reduces duplication in symbol table checking and manipulation across visitors.
    """
    
    def check_symbol_table_for_duplicates(self, symbol_table, new_symbol_name, code_range):
        """
        Check if a symbol already exists in the given symbol table.
        
        Args:
            symbol_table: SymbolsTable to check
            new_symbol_name: Name of the symbol to check
            code_range: CodeRange for error reporting
            
        Raises:
            GeLBExSymbolExists: If the symbol already exists
        """
        if symbol_table and symbol_table.contains_local(new_symbol_name):
            existing_symbol = symbol_table.get_symbol_definition_local(new_symbol_name)
            raise GeLBExSymbolExists(
                code_range.start_line, code_range.start_column,
                f"Symbol '{new_symbol_name}' is already defined",
                f"Previous definition at {existing_symbol.value.code_range}"
            )
    
    def create_symbol_definition(self, name, tag, value):
        """
        Factory method for creating SymbolDefinition objects.
        
        Args:
            name: Symbol name (string)
            tag: Symbol tag/type (string)
            value: Symbol value (AST node)
            
        Returns:
            SymbolDefinition object
        """
        from gelb.gelb_ast.SymbolDefinition import SymbolDefinition
        return SymbolDefinition(name=name, tag=tag, value=value)
    
    def ensure_symbol_table_exists(self, node, parent_table=None):
        """
        Ensure a node has a symbol table, creating one if necessary.
        
        Args:
            node: AST node that should have a symbol_defs attribute
            parent_table: Optional parent table for hierarchical lookup
        """
        if not hasattr(node, 'symbol_defs') or node.symbol_defs is None:
            from gelb.frontend.SymbolsTable import SymbolsTable
            node.symbol_defs = SymbolsTable(parent_table=parent_table)