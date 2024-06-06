#!/usr/bin/env python3

from frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb_ast.ASTNodes import *


class ImplicitSymbolsAdderVisitor(ASTBaseVisitor):
    """
    Concrete visitor for adding to symbol_defs tables the symbols
    corresponding to the implicit variables & constants.

    NOTE: Should be invoked *after* SymbolsTablesBuilderVisitor (
    build_symbols_tables).
    """
    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        raise NotImplementedError()
