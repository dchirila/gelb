#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.gelb_ast.ASTNodes import *


class ConstantsResolverVisitor(ASTBaseVisitor):
    """
    Concrete visitor for resolving ALL constants:
    - explicit AND implicit,
    - in AND scopes.

    As implicit constants, we need to resolve:
    - D ~> the dimensionality of the simulation
    - Q ~> the number of DFs of each lattice
    - Nx ~> size of the simulation domain along the X axis
    - [optional, if D>1] Ny ~> size of the simulation domain along the Y axis
    - [optional, if D>2] Nz ~> size of the simulation domain along the Z axis
    """
    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        # resolve constants @GlobalConstantsBlock_N
        if node.global_constants is not None:
            node.global_constants = self.visit(
                node.global_constants, ast_root_node
            )
        
        # resolve constants @LatticesBlock_N
        if node.lattices is not None:
            node.lattices = self.visit(
                node.lattices, ast_root_node
            )
        return node

    def visitGlobalConstantsBlock_N(
            self,
            node: GlobalConstantsBlock_N,
            ast_root_node: Program_N
    ):
        for stmt in node.stmts:  # iterate over statements
            # first, get all symbol references @current statement
            referenced_symbols_rhs = stmt.value.get_referenced_symbols()
            # then, we obtain a set (no repetitions) of symbol reference
            # names, s.t. we can invoke =replace_symbol_references=
            referenced_symbols_names_rhs = set()
            for sref in referenced_symbols_rhs:
                referenced_symbols_names_rhs.add(
                    sref.name
                )
            # next, we iterate over the names of the referenced symbols,
            # and replace all of their occurrences with the actual definitions
            # NOTE: when we replace symbol occurrences, they are also
            #       automatically reflected in the SymbolsTable
            for srefname in referenced_symbols_names_rhs:
                sdef = node.symbol_defs.get_symbol_definition(
                    srefname
                ).value.value
                stmt.value.replace_symbol_references(
                    srefname,
                    sdef
                )
        return node

    def visitLatticesBlock_N(
            self,
            node: LatticesBlock_N,
            ast_root_node: Program_N
    ):
        """Resolve constants in lattice instantiation statements."""
        for stmt in node.stmts:  # iterate over lattice statements
            self.visit(stmt, ast_root_node)
        return node

    def visitLatticeInstaStmt_N(
            self,
            node: LatticeInstaStmt_N,
            ast_root_node: Program_N
    ):
        """Resolve constants in lattice instantiation parameters."""
        # Get the lattices block's symbol table which has hierarchical access to global constants
        parent_lattices_block = self._find_parent_lattices_block(ast_root_node)
        if parent_lattices_block is None or parent_lattices_block.symbol_defs is None:
            return node
        
        # Resolve constants in all parameter expressions
        expressions_to_resolve = [
            (node.d, "d parameter"),
            (node.q, "q parameter")
        ]
        
        # Add new parameters if they exist
        if hasattr(node, 'grid_size') and node.grid_size is not None:
            expressions_to_resolve.append((node.grid_size, "grid_size parameter"))
        if hasattr(node, 'periodicity') and node.periodicity is not None:
            expressions_to_resolve.append((node.periodicity, "periodicity parameter"))
        
        # Resolve constants in each expression
        for expr, description in expressions_to_resolve:
            if expr is not None:
                self._resolve_constants_in_expression(expr, parent_lattices_block.symbol_defs)
        
        return node

    def _resolve_constants_in_expression(self, expr, symbol_table):
        """Helper method to resolve constants in a single expression using hierarchical lookup."""
        # Get all symbol references in the expression
        referenced_symbols = expr.get_referenced_symbols()
        
        # Get unique symbol names
        referenced_symbols_names = set()
        for sref in referenced_symbols:
            referenced_symbols_names.add(sref.name)
        
        # Replace each referenced symbol with its definition
        for srefname in referenced_symbols_names:
            if symbol_table.contains(srefname):  # Uses hierarchical lookup
                sdef = symbol_table.get_symbol_definition(srefname).value.value
                expr.replace_symbol_references(srefname, sdef)

    def _find_parent_lattices_block(self, ast_root_node):
        """Find the lattices block in the program."""
        if hasattr(ast_root_node, 'lattices') and ast_root_node.lattices is not None:
            return ast_root_node.lattices
        return None
