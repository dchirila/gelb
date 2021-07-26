#!/usr/bin/env python3

from gelb.ASTBaseVisitor import ASTBaseVisitor
from gelb.ASTNodes import *


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
