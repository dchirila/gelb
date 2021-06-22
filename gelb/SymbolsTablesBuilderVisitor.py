#!/usr/bin/env python3

from gelb.ASTBaseVisitor import ASTBaseVisitor
from gelb.ASTNodes import *


class SymbolsTablesBuilderVisitor(ASTBaseVisitor):
    """
    Concrete visitor for adding the symbols tables to the AST nodes which
    need them.

    We need to distinguish between {global,local} symbols tables.
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
                    node.symbols.add_symbol({
                        'name': initializer.name.name,
                        'tag': "initializer",
                        'value': initializer
                    })

                    # trigger symbols-table creation @initializer
                    node.initializers[index] = self.visit(
                        node.initializers[index], ast_root_node
                    )

            # ... add dynamic-names to the program's global symbols table
            if node.dynamics is not None:
                for index, dynamic in enumerate(node.dynamics):
                    # add symbol for dynamic itself to the global symbols
                    # table
                    node.symbols.add_symbol({
                        'name': dynamic.name.name,
                        'tag': "dynamic",
                        'value': dynamic
                    })

                    # trigger symbols-table creation @dynamic
                    node.dynamics[index] = self.visit(
                        node.dynamics[index], ast_root_node
                    )

            # ... add gauge-names to the program's global symbols table
            if node.gauges is not None:
                for index, gauge in enumerate(node.gauges):
                    # add symbol for gauge itself to the global symbols
                    # table
                    node.symbols.add_symbol({
                        'name': gauge.name.name,
                        'tag': "gauge",
                        'value': gauge
                    })

                    # trigger symbols-table creation @gauge
                    node.gauges[index] = self.visit(
                        node.gauges[index], ast_root_node
                    )
            # END :: build global (program-wide) symbols table #

            if node.node_classes is not None:
                # trigger symbols-table creation @node-classes block
                node.node_classes = self.visit(node.node_classes, ast_root_node)

        return node

    def visitGlobalConstantsBlock_N(
            self,
            node: GlobalConstantsBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbols is None:
            node.symbols = SymbolsTable()

            for constant_insta_stmt in node.stmts:
                node.symbols.add_symbol({
                    'name': constant_insta_stmt.name.name,
                    'tag': "constant definition",
                    'value': constant_insta_stmt
                })
        return node

    def visitLatticesBlock_N(
            self,
            node: LatticesBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbols is None:
            node.symbols = SymbolsTable()

            for lattice_insta_stmt in node.stmts:
                node.symbols.add_symbol({
                    'name': lattice_insta_stmt.name.name,
                    'tag': 'lattice instance',
                    'value': lattice_insta_stmt
                })
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
                    node.symbols.add_symbol({
                        'name': stmt.name.name,
                        'tag': "constant definition",
                        'value': stmt
                    })
                elif isinstance(stmt, VariableDeclarationStmt_N):
                    node.symbols.add_symbol({
                        'name': stmt.name.name,
                        'tag': "variable declaration",
                        'value': stmt
                    })
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
                    node.symbols.add_symbol({
                        'name': stmt.name.name,
                        'tag': "constant definition",
                        'value': stmt
                    })
                elif isinstance(stmt, VariableDeclarationStmt_N):
                    node.symbols.add_symbol({
                        'name': stmt.name.name,
                        'tag': "variable declaration",
                        'value': stmt
                    })
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
                    node.symbols.add_symbol({
                        'name': stmt.name.name,
                        'tag': "constant definition",
                        'value': stmt
                    })
                elif isinstance(stmt, VariableDeclarationStmt_N):
                    node.symbols.add_symbol({
                        'name': stmt.name.name,
                        'tag': "variable declaration",
                        'value': stmt
                    })
        return node
