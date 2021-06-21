#!/usr/bin/env python3

from gelb.ASTBaseVisitor import ASTBaseVisitor
from gelb.ASTNodes import *


class SymbolsTablesBuilderVisitor(ASTBaseVisitor):
    """
    Concrete visitor for adding the symbols tables to the AST nodes which
    need them.

    We need to distinguish between {global,local} symbols tables:

    (1) Global symbols tables:

        TODO

    (2) Local symbols tables:

        TODO
    """

    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        # NOTE: The ast_root_node is redundant here (because it should be the
        # same as the node argument). However, we keep it for consistency (it
        # is NOT the same as node for sub-ast nodes).

        # first of all, build global (program-wide) symbols table
        if node.global_constants is not None:
            node.global_constants = self.visit(node.global_constants,
                                               ast_root_node)
        if node.lattices is not None:
            node.lattices = self.visit(node.lattices, ast_root_node)

        # TODO ... visit more nodes, to build more symbols tables ...

        return node

    def visitGlobalConstantsBlock_N(
            self,
            node: GlobalConstantsBlock_N,
            ast_root_node: Program_N
    ):
        # guard against attempts to build the symbols-table twice
        if node.symbols is None:
            node.symbols = SymbolsTable()  # new SymbolsTable

            for constant_insta_stmt in node.stmts:
                symbol_dict = {
                    'name': constant_insta_stmt.name.name,
                    'type': constant_insta_stmt.data_type,
                    'value': constant_insta_stmt
                }
                node.symbols.add_symbol(symbol_dict)
        return node

    def visitLatticesBlock_N(
            self,
            node: LatticesBlock_N,
            ast_root_node: Program_N
    ):
        # guard against attempts to build the symbols-table twice
        if node.symbols is None:
            node.symbols = SymbolsTable()  # new SymbolsTable

            for lattice_insta_stmt in node.stmts:
                symbol_dict = {
                    'name': lattice_insta_stmt.name.name,
                    'type': 'lattice instance',
                    'value': lattice_insta_stmt
                }
                node.symbols.add_symbol(symbol_dict)
        return node
