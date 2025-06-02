#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.gelb_ast.ASTNodes import *
from gelb.frontend.SymbolsTable import SymbolsTable
from gelb.gelb_ast.SymbolDefinition import SymbolDefinition
from gelb.utils.exceptions import (
    GeLBExSymbolUnknown,
    GeLBExSymbolRefBeforeDef,
    GeLBExSymbolConstantRecursion,
    GeLBExIncorrectStagesOrdering
)


class SymbolsTablesBuilderVisitor(ASTBaseVisitor):
    """
    Concrete visitor for adding the symbol_defs tables to the AST nodes which
    need them.

    We need to distinguish between {global,local} symbol_defs tables.
    """
    def __init__(self, symbol_to_ignore_for_testing=None):
        if symbol_to_ignore_for_testing is not None:
            self.implicit_symbols = [symbol_to_ignore_for_testing]
        else:
            self.implicit_symbols = []
        # Store global constants symbol table for hierarchical lookup
        self.global_constants_symbol_table = None

    def check_for_undef_or_ref_before_def_symbols(self, node, ast_root=None):
        """
        Method to check for undefined (or referenced-before-defined) symbols.

        NOTE: It is more efficient & convenient to perform the
        referenced-before-defined check here.
        """
        if node.symbol_defs is not None:
            # check that all referenced symbols were actually defined
            for sref in node.get_referenced_symbols():
                if not node.symbol_defs.contains(sref.name):
                    if (
                            isinstance(node, InitializerBlock_N) or
                            isinstance(node, DynamicBlock_N) or
                            isinstance(node, GaugeBlock_N) or
                            isinstance(node, GeometryBlock_N)
                    ):
                        lattice_names = []
                        if (
                                (ast_root is not None) and
                                isinstance(ast_root, Program_N) and
                                ast_root.lattices is not None
                        ):
                            lattice_sdefs = ast_root.lattices.symbol_defs
                            lattice_names = [
                                lat_def.name for lat_def in lattice_sdefs
                            ]
                        self.implicit_symbols += [
                            # TODO un-define y, z, NY, Nz, depending on
                            #  dimensionality (inferred from ast_root)
                            "x", "y", "z", "Nx", "Ny", "Nz"
                        ]
                        # Add block name only if it has a name attribute
                        if hasattr(node, 'name') and node.name is not None:
                            self.implicit_symbols.append(str(node.name.name))
                        self.implicit_symbols += lattice_names
                        
                        # For geometry block, also need to check global symbol table for node classes
                        if isinstance(node, GeometryBlock_N) and ast_root is not None:
                            # Check if symbol is in the global symbol table (e.g., node classes)
                            if ast_root.symbol_defs and ast_root.symbol_defs.contains(sref.name):
                                continue  # Symbol found in global scope, skip the error

                    if sref.name not in self.implicit_symbols:
                        raise GeLBExSymbolUnknown(sref)
                else:
                    # OK, symbol *is* in the symbols table (but is it
                    # referenced before it is defined?)
                    sdef = node.symbol_defs.get_symbol_definition(sref.name)
                    if sdef.value.code_range > sref.code_range:
                        raise GeLBExSymbolRefBeforeDef(sref, sdef)
        else:
            raise GeLBExIncorrectStagesOrdering(
                error=(
                    f"Attempted to invoke"
                    f" \"check_for_undef_or_ref_before_def_symbols\","
                    f" but the symbol-definitions table for {node} has not"
                    f" been constructed yet."
                )
            )

    def check_for_recursively_defined_symbols(self, node, ast_root=None):
        if node.symbol_defs is not None:
            for sdef in node.symbol_defs:
                if sdef.tag == "constant definition":
                    # check that no constant is defined in terms of itself
                    sdefval = sdef.value
                    referenced_symbols = sdefval.value.get_referenced_symbols()
                    for symbol_ref in referenced_symbols:
                        if symbol_ref.name == sdef.name:
                            raise GeLBExSymbolConstantRecursion(symbol_ref)
        else:
            raise GeLBExIncorrectStagesOrdering(
                error=(
                    f"Attempted to invoke"
                    f" \"check_for_recursively_defined_symbols\","
                    f" but the symbol-definitions table for {node} has not"
                    f" been constructed yet."
                )
            )

    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        # NOTE: The ast_root_node is redundant here (because it should be the
        # same as the node argument). However, we keep it for consistency (it
        # is NOT the same as node for sub-ast nodes).

        # guard against attempts to build the symbol_defs-table more than once
        if node.symbol_defs is None:
            if node.global_constants is not None:
                # trigger symbol_defs-table creation @global constants block
                node.global_constants = self.visit(node.global_constants,
                                                   ast_root_node)
                # Store global constants symbol table for use in other blocks
                self.global_constants_symbol_table = node.global_constants.symbol_defs
            else:
                # Create an empty global constants symbol table even if the block doesn't exist
                # This ensures all other blocks have a consistent parent for hierarchical lookup
                self.global_constants_symbol_table = SymbolsTable()
            
            # Create program's global symbol table with global constants as parent
            # This allows the program table to contain node classes while still accessing constants
            node.symbol_defs = SymbolsTable(parent_table=self.global_constants_symbol_table)
            if node.lattices is not None:
                # trigger symbol_defs-table creation @lattices block
                node.lattices = self.visit(node.lattices, ast_root_node)

            # BEGIN :: build global (program-wide) symbol_defs table #
            # ... add initializer-names to the program's global symbol_defs
            # table
            if node.initializers is not None:
                for index, initializer in enumerate(node.initializers):
                    # add symbol for initializer itself to the global
                    # symbol_defs table
                    node.symbol_defs.append(
                        SymbolDefinition(
                            name=initializer.name.name,
                            tag="initializer",
                            value=initializer
                        )
                    )

                    # trigger symbol_defs-table creation @initializer
                    node.initializers[index] = self.visit(
                        node.initializers[index], ast_root_node
                    )

            # ... add dynamic-names to the program's global symbol_defs table
            if node.dynamics is not None:
                for index, dynamic in enumerate(node.dynamics):
                    # add symbol for dynamic itself to the global symbol_defs
                    # table
                    node.symbol_defs.append(
                        SymbolDefinition(
                            name=dynamic.name.name,
                            tag="dynamic",
                            value=dynamic
                        )
                    )

                    # trigger symbol_defs-table creation @dynamic
                    node.dynamics[index] = self.visit(
                        node.dynamics[index], ast_root_node
                    )

            # ... add gauge-names to the program's global symbol_defs table
            if node.gauges is not None:
                for index, gauge in enumerate(node.gauges):
                    # add symbol for gauge itself to the global symbol_defs
                    # table
                    node.symbol_defs.append(
                        SymbolDefinition(
                            name=gauge.name.name,
                            tag="gauge",
                            value=gauge
                        )
                    )

                    # trigger symbol_defs-table creation @gauge
                    node.gauges[index] = self.visit(
                        node.gauges[index], ast_root_node
                    )
            # END :: build global (program-wide) symbol_defs table #

            if node.node_classes is not None:
                # trigger symbol_defs-table creation @node-classes block
                node.node_classes = self.visit(node.node_classes, ast_root_node)
                
                # Add node class names to global symbol table so geometry can reference them
                for node_class_stmt in node.node_classes.stmts:
                    node.symbol_defs.append(
                        SymbolDefinition(
                            name=node_class_stmt.name.name,
                            tag="node class",
                            value=node_class_stmt
                        )
                    )
                
            if node.geometry is not None:
                # trigger symbol_defs-table creation @geometry block
                node.geometry = self.visit(node.geometry, ast_root_node)

        return node

    def visitGlobalConstantsBlock_N(
            self,
            node: GlobalConstantsBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbol_defs is None:
            node.symbol_defs = SymbolsTable()

            for constant_insta_stmt in node.stmts:
                node.symbol_defs.append(
                    SymbolDefinition(
                        name=constant_insta_stmt.name.name,
                        tag="constant definition",
                        value=constant_insta_stmt
                    )
                )
            self.check_for_undef_or_ref_before_def_symbols(node, ast_root_node)
            self.check_for_recursively_defined_symbols(node, ast_root_node)
        return node

    def visitLatticesBlock_N(
            self,
            node: LatticesBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbol_defs is None:
            # Create symbol table with global constants as parent
            node.symbol_defs = SymbolsTable(parent_table=self.global_constants_symbol_table)

            for lattice_insta_stmt in node.stmts:
                node.symbol_defs.append(
                    SymbolDefinition(
                        name=lattice_insta_stmt.name.name,
                        tag='lattice instance',
                        value=lattice_insta_stmt
                    )
                )
            self.check_for_undef_or_ref_before_def_symbols(node, ast_root_node)
        return node

    def visitInitializerBlock_N(
            self,
            node: InitializerBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbol_defs is None:
            # Create symbol table with global constants as parent
            node.symbol_defs = SymbolsTable(parent_table=self.global_constants_symbol_table)

            for stmt in node.stmts:
                if isinstance(stmt, ConstantDefinitionStmt_N):
                    node.symbol_defs.append(
                        SymbolDefinition(
                            name=stmt.name.name,
                            tag="constant definition",
                            value=stmt
                        )
                    )
                elif isinstance(stmt, VariableDeclarationStmt_N):
                    node.symbol_defs.append(
                        SymbolDefinition(
                            name=stmt.name.name,
                            tag="variable declaration",
                            value=stmt
                        )
                    )
            self.check_for_undef_or_ref_before_def_symbols(node, ast_root_node)
            self.check_for_recursively_defined_symbols(node, ast_root_node)
        return node

    def visitDynamicBlock_N(
            self,
            node: DynamicBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbol_defs is None:
            # Create symbol table with global constants as parent
            node.symbol_defs = SymbolsTable(parent_table=self.global_constants_symbol_table)

            for stmt in node.stmts:
                if isinstance(stmt, ConstantDefinitionStmt_N):
                    node.symbol_defs.append(
                        SymbolDefinition(
                            name=stmt.name.name,
                            tag="constant definition",
                            value=stmt
                        )
                    )
                elif isinstance(stmt, VariableDeclarationStmt_N):
                    node.symbol_defs.append(
                        SymbolDefinition(
                            name=stmt.name.name,
                            tag="variable declaration",
                            value=stmt
                        )
                    )
            self.check_for_undef_or_ref_before_def_symbols(node, ast_root_node)
            self.check_for_recursively_defined_symbols(node, ast_root_node)
        return node

    def visitGaugeBlock_N(
            self,
            node: GaugeBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbol_defs is None:
            # Create symbol table with global constants as parent
            node.symbol_defs = SymbolsTable(parent_table=self.global_constants_symbol_table)

            for stmt in node.stmts:
                if isinstance(stmt, ConstantDefinitionStmt_N):
                    node.symbol_defs.append(
                        SymbolDefinition(
                            name=stmt.name.name,
                            tag="constant definition",
                            value=stmt
                        )
                    )
                elif isinstance(stmt, VariableDeclarationStmt_N):
                    node.symbol_defs.append(
                        SymbolDefinition(
                            name=stmt.name.name,
                            tag="variable declaration",
                            value=stmt
                        )
                    )
            for var_decl in node.outputs:
                node.symbol_defs.append(
                    SymbolDefinition(
                        name=var_decl.name.name,
                        tag="output variable declaration",
                        value=var_decl
                    )
                )
            self.check_for_undef_or_ref_before_def_symbols(node, ast_root_node)
            self.check_for_recursively_defined_symbols(node, ast_root_node)
        return node

    def visitNodeClassesBlock_N(
            self,
            node: NodeClassesBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbol_defs is None:
            # Create symbol table with global constants as parent
            node.symbol_defs = SymbolsTable(parent_table=self.global_constants_symbol_table)

            for node_class_insta_stmt in node.stmts:
                node.symbol_defs.append(
                    SymbolDefinition(
                        name=node_class_insta_stmt.name.name,
                        tag='node class',
                        value=node_class_insta_stmt
                    )
                )
        return node

    def visitGeometryBlock_N(
            self,
            node: GeometryBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbol_defs is None:
            # Create symbol table with program's global table as parent
            # This allows geometry to access both global constants (via program->global_constants)
            # and node classes (directly from program's global table)
            node.symbol_defs = SymbolsTable(parent_table=ast_root_node.symbol_defs)
            
            # Geometry block doesn't define any symbols itself,
            # it just needs access to global constants and node classes for expressions
            self.check_for_undef_or_ref_before_def_symbols(node, ast_root_node)
        return node
