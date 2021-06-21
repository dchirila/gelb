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

        # guard against attempts to build the symbols-table more than once
        if node.symbols is None:
            node.symbols = SymbolsTable()  # new SymbolsTable

            if node.global_constants is not None:
                # trigger symbols-table creation @global constants block
                node.global_constants = self.visit(node.global_constants,
                                                   ast_root_node)
            if node.lattices is not None:
                # trigger symbols-table creation @lattices block
                node.lattices = self.visit(node.lattices, ast_root_node)

            # BEGIN :: build global (program-wide) symbols table #
            # ... add initializer-names to the program's global symbols table
            if node.initializers is not None:
                for index, initializer in enumerate(node.initializers):
                    # add symbol for initializer itself to the global symbols
                    # table
                    symbol_dict = {
                        'name': initializer.name.name,
                        'type': "initializer",
                        'value': initializer
                    }
                    node.symbols.add_symbol(symbol_dict)

                    # trigger symbols-table creation @initializer
                    node.initializers[index] = self.visit(
                        node.initializers[index], ast_root_node
                    )

            # ... add dynamic-names to the program's global symbols table
            if node.dynamics is not None:
                for index, dynamic in enumerate(node.dynamics):
                    # add symbol for dynamic itself to the global symbols
                    # table
                    symbol_dict = {
                        'name': dynamic.name.name,
                        'type': "dynamic",
                        'value': dynamic
                    }
                    node.symbols.add_symbol(symbol_dict)

                    # trigger symbols-table creation @dynamic
                    node.dynamics[index] = self.visit(
                        node.dynamics[index], ast_root_node
                    )

            # ... add gauge-names to the program's global symbols table
            if node.gauges is not None:
                for index, gauge in enumerate(node.gauges):
                    # add symbol for gauge itself to the global symbols
                    # table
                    symbol_dict = {
                        'name': gauge.name.name,
                        'type': "gauge",
                        'value': gauge
                    }
                    node.symbols.add_symbol(symbol_dict)

                    # trigger symbols-table creation @gauge
                    node.gauges[index] = self.visit(
                        node.gauges[index], ast_root_node
                    )
            # END :: build global (program-wide) symbols table #

            # TODO ... visit more nodes, to build more symbols tables ...

        return node

    def visitGlobalConstantsBlock_N(
            self,
            node: GlobalConstantsBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbols is None:
            node.symbols = SymbolsTable()

            for constant_insta_stmt in node.stmts:
                symbol_dict = {
                    'name': constant_insta_stmt.name.name,
                    'type': "constant definition",
                    'value': constant_insta_stmt
                }
                node.symbols.add_symbol(symbol_dict)
        return node

    def visitLatticesBlock_N(
            self,
            node: LatticesBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbols is None:
            node.symbols = SymbolsTable()

            for lattice_insta_stmt in node.stmts:
                symbol_dict = {
                    'name': lattice_insta_stmt.name.name,
                    'type': 'lattice instance',
                    'value': lattice_insta_stmt
                }
                node.symbols.add_symbol(symbol_dict)
        return node

    def visitInitializerBlock_N(
            self,
            node: InitializerBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbols is None:
            node.symbols = SymbolsTable()

            for stmt in node.stmts:
                if isinstance(stmt, ConstantDefinitionStmt_N):
                    symbol_dict = {
                        'name': stmt.name.name,
                        'type': "constant definition",
                        'value': stmt
                    }
                    node.symbols.add_symbol(symbol_dict)
                elif isinstance(stmt, VariableDeclarationStmt_N):
                    symbol_dict = {
                        'name': stmt.name.name,
                        'type': "variable declaration",
                        'value': stmt
                    }
                    node.symbols.add_symbol(symbol_dict)
        return node

    def visitDynamicBlock_N(
            self,
            node: DynamicBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbols is None:
            node.symbols = SymbolsTable()

            for stmt in node.stmts:
                if isinstance(stmt, ConstantDefinitionStmt_N):
                    symbol_dict = {
                        'name': stmt.name.name,
                        'type': "constant definition",
                        'value': stmt
                    }
                    node.symbols.add_symbol(symbol_dict)
                elif isinstance(stmt, VariableDeclarationStmt_N):
                    symbol_dict = {
                        'name': stmt.name.name,
                        'type': "variable declaration",
                        'value': stmt
                    }
                    node.symbols.add_symbol(symbol_dict)
        return node

    def visitGaugeBlock_N(
            self,
            node: GaugeBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbols is None:
            node.symbols = SymbolsTable()

            for stmt in node.stmts:
                if isinstance(stmt, ConstantDefinitionStmt_N):
                    symbol_dict = {
                        'name': stmt.name.name,
                        'type': "constant definition",
                        'value': stmt
                    }
                    node.symbols.add_symbol(symbol_dict)
                elif isinstance(stmt, VariableDeclarationStmt_N):
                    symbol_dict = {
                        'name': stmt.name.name,
                        'type': "variable declaration",
                        'value': stmt
                    }
                    node.symbols.add_symbol(symbol_dict)
        return node
