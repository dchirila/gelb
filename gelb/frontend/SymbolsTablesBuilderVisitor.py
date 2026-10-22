#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.implicit_symbols import (
    dimensionality_from_program,
    implicit_symbols_for_block,
)
from gelb.frontend.visitor_mixins import SymbolTableUtilityMixin
from gelb.gelb_ast.ASTNodes import *
from gelb.frontend.SymbolsTable import SymbolsTable
from gelb.gelb_ast.SymbolDefinition import SymbolDefinition
from gelb.utils.exceptions import (
    GeLBExSymbolUnknown,
    GeLBExSymbolRefBeforeDef,
    GeLBExSymbolConstantRecursion,
    GeLBExIncorrectStagesOrdering
)


class SymbolsTablesBuilderVisitor(ASTBaseVisitor, SymbolTableUtilityMixin):
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
        # Every block's symbol table has Program.symbol_defs as its parent for
        # hierarchical lookup, so the global constants need no table here.

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
                    unresolved_symbols_to_allow = set(self.implicit_symbols)
                    if (
                            isinstance(node, InitializerBlock_N) or
                            isinstance(node, DynamicBlock_N) or
                            isinstance(node, GaugeBlock_N) or
                            isinstance(node, GeometryBlock_N) or
                            isinstance(node, FunctionBlock_N)
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
                        dimensionality = dimensionality_from_program(ast_root)
                        unresolved_symbols_to_allow.update(
                            implicit_symbols_for_block(node, dimensionality)
                        )
                        # Add block name only if it has a name attribute
                        if hasattr(node, 'name') and node.name is not None:
                            unresolved_symbols_to_allow.add(
                                str(node.name.name)
                            )
                        unresolved_symbols_to_allow.update(lattice_names)
                        
                        # For geometry block, also need to check global symbol table for node classes
                        if isinstance(node, GeometryBlock_N) and ast_root is not None:
                            # Check if symbol is in the global symbol table (e.g., node classes)
                            if ast_root.symbol_defs and ast_root.symbol_defs.contains(sref.name):
                                continue  # Symbol found in global scope, skip the error

                    if sref.name not in unresolved_symbols_to_allow:
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
            # Create Program.symbol_defs as the root table (no parent)
            node.symbol_defs = SymbolsTable(parent_table=None)
            
            if node.global_constants is not None:
                # trigger symbol_defs-table creation @global constants block
                node.global_constants = self.visit(node.global_constants,
                                                   ast_root_node)
                # Promote global constants to Program level
                self._promote_global_constants_to_program(node.global_constants, node)
            if node.lattices is not None:
                # trigger symbol_defs-table creation @lattices block
                node.lattices = self.visit(node.lattices, ast_root_node)
                # Promote lattices to Program level
                self._promote_lattices_to_program(node.lattices, node)

            # BEGIN :: build global (program-wide) symbol_defs table #
            # ... add function-names to the program's global symbol_defs table
            # (before other blocks so functions can be called from them)
            if node.functions is not None:
                for index, function in enumerate(node.functions):
                    node.symbol_defs.append(
                        SymbolDefinition(
                            name=function.name.name,
                            tag="function",
                            value=function
                        )
                    )
                    node.functions[index] = self.visit(
                        node.functions[index], ast_root_node
                    )

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
            # Create symbol table with Program.symbol_defs as parent  
            node.symbol_defs = SymbolsTable(parent_table=ast_root_node.symbol_defs)

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
            # Create symbol table with Program.symbol_defs as parent
            node.symbol_defs = SymbolsTable(parent_table=ast_root_node.symbol_defs)

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
            # Create symbol table with Program.symbol_defs as parent
            node.symbol_defs = SymbolsTable(parent_table=ast_root_node.symbol_defs)

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
            # Create symbol table with Program.symbol_defs as parent
            node.symbol_defs = SymbolsTable(parent_table=ast_root_node.symbol_defs)

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
            # Create symbol table with Program.symbol_defs as parent
            node.symbol_defs = SymbolsTable(parent_table=ast_root_node.symbol_defs)

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

    def visitFunctionBlock_N(
            self,
            node: FunctionBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbol_defs is None:
            node.symbol_defs = SymbolsTable(parent_table=ast_root_node.symbol_defs)

            # Register input parameters
            for param in node.inputs:
                node.symbol_defs.append(
                    SymbolDefinition(
                        name=param.name.name,
                        tag="input parameter",
                        value=param
                    )
                )

            # Register output parameters
            for param in node.outputs:
                node.symbol_defs.append(
                    SymbolDefinition(
                        name=param.name.name,
                        tag="output parameter",
                        value=param
                    )
                )

            # Register local variables and constants from body
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

    def visitNodeClassesBlock_N(
            self,
            node: NodeClassesBlock_N,
            ast_root_node: Program_N
    ):
        if node.symbol_defs is None:
            # Create symbol table with Program.symbol_defs as parent
            node.symbol_defs = SymbolsTable(parent_table=ast_root_node.symbol_defs)

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
    
    def _promote_global_constants_to_program(self, global_constants_block, program_node):
        """
        Promote global constants from GlobalConstantsBlock to Program level.
        This allows all blocks to access global constants through the Program.symbol_defs hierarchy.
        """
        if global_constants_block.symbol_defs:
            for symbol_def in global_constants_block.symbol_defs.symbol_defs:
                # Add each global constant to the Program's symbol table
                program_node.symbol_defs.append(symbol_def)
    
    def _promote_lattices_to_program(self, lattices_block, program_node):
        """
        Promote lattices from LatticesBlock to Program level.
        This allows all blocks to access lattice references through the Program.symbol_defs hierarchy.
        """
        if lattices_block.symbol_defs:
            for symbol_def in lattices_block.symbol_defs.symbol_defs:
                # Add each lattice to the Program's symbol table
                program_node.symbol_defs.append(symbol_def)
