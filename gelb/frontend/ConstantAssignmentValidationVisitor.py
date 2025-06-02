#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.visitor_mixins import SymbolTableUtilityMixin
from gelb.utils.exceptions import GeLBExConstantAssignment


class ConstantAssignmentValidationVisitor(ASTBaseVisitor, SymbolTableUtilityMixin):
    """
    Validates that constants are not assigned to in variable assignment statements.
    
    This visitor enforces the rule that constants (symbols with tag "constant definition"
    or "implicit dimension constant") cannot appear on the left-hand side of variable
    assignment statements.
    """

    def visitProgram_N(self, node, ast_root_node):
        """Visit all blocks in the program."""
        for block in [node.global_constants, node.lattices, node.node_classes, node.geometry]:
            if block:
                self.visit(block, ast_root_node)
        
        # Visit all initializers, dynamics, and gauges
        for block_list in [node.initializers, node.dynamics, node.gauges]:
            if block_list:
                for block in block_list:
                    if block:
                        self.visit(block, ast_root_node)
        
        return node

    def visitGlobalConstantsBlock_N(self, node, ast_root_node):
        """Visit all statements in global constants block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node

    def visitLatticesBlock_N(self, node, ast_root_node):
        """Visit all statements in lattices block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node

    def visitNodeClassesBlock_N(self, node, ast_root_node):
        """Visit all statements in node classes block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node

    def visitGeometryBlock_N(self, node, ast_root_node):
        """Visit all statements in geometry block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node

    def visitInitializerBlock_N(self, node, ast_root_node):
        """Visit all statements in initializer block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node

    def visitDynamicBlock_N(self, node, ast_root_node):
        """Visit all statements in dynamic block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node

    def visitGaugeBlock_N(self, node, ast_root_node):
        """Visit all statements in gauge block."""
        for stmt in node.stmts:
            self.visit(stmt, ast_root_node)
        return node

    def visitVariableAssignmentStmt_N(self, node, ast_root_node):
        """
        Validate that the LHS of variable assignment is not a constant.
        
        This is the core validation: check if the identifier on the left-hand side
        of the assignment is a constant, and if so, raise an error.
        """
        # Check if LHS is an identifier (it should be for variable assignments)
        lhs_identifier = node.lhs
        if hasattr(lhs_identifier, 'name'):
            symbol_name = str(lhs_identifier.name)
            
            # Find the symbol definition using hierarchical lookup
            symbol_def = self._find_symbol_definition(symbol_name, ast_root_node)
            
            if symbol_def:
                # Check if this symbol is a constant
                if (symbol_def.tag == "constant definition" or 
                    symbol_def.tag == "implicit dimension constant"):
                    raise GeLBExConstantAssignment(lhs_identifier, symbol_def)
        
        # Continue visiting the RHS
        self.visit(node.rhs, ast_root_node)
        return node

    def _find_symbol_definition(self, symbol_name, ast_root_node):
        """
        Find a symbol definition by searching through the symbol table hierarchy.
        
        This method searches through the global constants and all block symbol tables
        to find the given symbol.
        
        Args:
            symbol_name: Name of the symbol to find
            ast_root_node: The root Program_N node containing all symbol tables
            
        Returns:
            SymbolDefinition if found, None otherwise
        """
        # First check global constants
        if ast_root_node.global_constants and ast_root_node.global_constants.symbol_defs:
            symbol_def = ast_root_node.global_constants.symbol_defs.get_symbol_definition(symbol_name)
            if symbol_def:
                return symbol_def
        
        # Then check all other blocks
        all_blocks = []
        
        # Add individual blocks
        if ast_root_node.lattices:
            all_blocks.append(ast_root_node.lattices)
        if ast_root_node.node_classes:
            all_blocks.append(ast_root_node.node_classes)
        if ast_root_node.geometry:
            all_blocks.append(ast_root_node.geometry)
            
        # Add block lists
        for block_list in [ast_root_node.initializers, ast_root_node.dynamics, ast_root_node.gauges]:
            if block_list:
                all_blocks.extend(block_list)
        
        # Search through all blocks
        for block in all_blocks:
            if block and hasattr(block, 'symbol_defs') and block.symbol_defs:
                symbol_def = block.symbol_defs.get_symbol_definition(symbol_name)
                if symbol_def:
                    return symbol_def
        
        return None

    # Default visitors for other node types (pass-through)
    def visitConstantDefinitionStmt_N(self, node, ast_root_node):
        """Visit constant definition statement (no validation needed)."""
        return node

    def visitVariableDeclarationStmt_N(self, node, ast_root_node):
        """Visit variable declaration statement (no validation needed)."""
        return node

    def visitLatticeInstaStmt_N(self, node, ast_root_node):
        """Visit lattice instantiation statement (no validation needed)."""
        return node

    def visitLatticeOutSelectionAssignmentStmt_N(self, node, ast_root_node):
        """Visit lattice output assignment statement (no validation needed)."""
        self.visit(node.rhs, ast_root_node)
        return node

    def visitArraySelectionAssignmentStmt_N(self, node, ast_root_node):
        """Visit array selection assignment statement (no validation needed)."""
        self.visit(node.rhs, ast_root_node)
        return node

    def visitPaintNodesStmt_N(self, node, ast_root_node):
        """Visit paint nodes statement (no validation needed)."""
        return node

    def visitNodeClassInstaStmt_N(self, node, ast_root_node):
        """Visit node class instantiation statement (no validation needed)."""
        return node

    def visitSetSimulationDescriptionStmt_N(self, node, ast_root_node):
        """Visit simulation description statement (no validation needed)."""
        return node

    def visitSetGridSizeStmt_N(self, node, ast_root_node):
        """Visit set grid size statement (no validation needed)."""
        return node

    def visitSetGridPeriodicityStmt_N(self, node, ast_root_node):
        """Visit set grid periodicity statement (no validation needed)."""
        return node

    # For expressions, we generally don't need to validate but should traverse
    def visitIdentifier_N(self, node, ast_root_node):
        """Visit identifier (no validation needed)."""
        return node

    def visitIntLiteral_N(self, node, ast_root_node):
        """Visit integer literal (no validation needed)."""
        return node

    def visitRealLiteral_N(self, node, ast_root_node):
        """Visit real literal (no validation needed)."""
        return node

    def visitBoolLiteral_N(self, node, ast_root_node):
        """Visit boolean literal (no validation needed)."""
        return node

    def visitStringLiteral_N(self, node, ast_root_node):
        """Visit string literal (no validation needed)."""
        return node

    def visitArrayLiteral1D_N(self, node, ast_root_node):
        """Visit 1D array literal (traverse elements)."""
        for element in node.elements:
            self.visit(element, ast_root_node)
        return node

    def visitArrayLiteral2D_N(self, node, ast_root_node):
        """Visit 2D array literal (traverse elements)."""
        for element in node.elements:
            self.visit(element, ast_root_node)
        return node

    def visitArrayLiteral3D_N(self, node, ast_root_node):
        """Visit 3D array literal (traverse elements)."""
        for element in node.elements:
            self.visit(element, ast_root_node)
        return node

    def visitArrayLiteral4D_N(self, node, ast_root_node):
        """Visit 4D array literal (traverse elements)."""
        for element in node.elements:
            self.visit(element, ast_root_node)
        return node

    # Binary operations
    def visitAdd_N(self, node, ast_root_node):
        """Visit addition expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    def visitSub_N(self, node, ast_root_node):
        """Visit subtraction expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    def visitMul_N(self, node, ast_root_node):
        """Visit multiplication expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    def visitDiv_N(self, node, ast_root_node):
        """Visit division expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    def visitPow_N(self, node, ast_root_node):
        """Visit power expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    # Comparison operations
    def visitLess_N(self, node, ast_root_node):
        """Visit less than expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    def visitGreater_N(self, node, ast_root_node):
        """Visit greater than expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    def visitLessEqual_N(self, node, ast_root_node):
        """Visit less than or equal expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    def visitGreaterEqual_N(self, node, ast_root_node):
        """Visit greater than or equal expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    def visitEqual_N(self, node, ast_root_node):
        """Visit equality expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    def visitNotEqual_N(self, node, ast_root_node):
        """Visit not equal expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    # Logical operations
    def visitAnd_N(self, node, ast_root_node):
        """Visit logical AND expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    def visitOr_N(self, node, ast_root_node):
        """Visit logical OR expression."""
        self.visit(node.left, ast_root_node)
        self.visit(node.right, ast_root_node)
        return node

    # Unary operations
    def visitUnaryMinusExpr_N(self, node, ast_root_node):
        """Visit unary minus expression."""
        self.visit(node.value, ast_root_node)
        return node

    def visitNotExpr_N(self, node, ast_root_node):
        """Visit logical NOT expression."""
        self.visit(node.value, ast_root_node)
        return node

    # Array and lattice selections
    def visitRectSelOfArrayElems_N(self, node, ast_root_node):
        """Visit rectangular selection of array elements."""
        self.visit(node.array_name, ast_root_node)
        for range_node in node.element_ranges:
            if range_node:
                self.visit(range_node, ast_root_node)
        return node

    def visitRectSelOfLatticeInDFs_N(self, node, ast_root_node):
        """Visit rectangular selection of lattice input distribution functions."""
        self.visit(node.lattice_name, ast_root_node)
        for range_node in node.element_ranges:
            if range_node:
                self.visit(range_node, ast_root_node)
        return node

    def visitRectSelOfLatticeOutDFs_N(self, node, ast_root_node):
        """Visit rectangular selection of lattice output distribution functions."""
        self.visit(node.lattice_name, ast_root_node)
        for range_node in node.element_ranges:
            if range_node:
                self.visit(range_node, ast_root_node)
        return node

    def visitRange_N(self, node, ast_root_node):
        """Visit range node."""
        if node.low:
            self.visit(node.low, ast_root_node)
        if node.high:
            self.visit(node.high, ast_root_node)
        return node

    def visitRangePlaceholder_N(self, node, ast_root_node):
        """Visit range placeholder (no validation needed)."""
        return node

    # Data types
    def visitScalarDataType_N(self, node, ast_root_node):
        """Visit scalar data type (no validation needed)."""
        return node

    def visitArrayDataType_N(self, node, ast_root_node):
        """Visit array data type (no validation needed)."""
        return node