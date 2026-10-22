#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import (
    GeLBExSymbolUnknown,
)


class GeometryInitialValidationVisitor(ASTBaseVisitor):
    """
    Concrete visitor for initial validation of the GeometryBlock_N.

    The main concern at this stage is to ensure that all of the node-classes
    referenced within the GeometryBlock_N are defined
    (inside the NodeClassesBlock_N).
    """
    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        for stmt in node.geometry.stmts:
            if isinstance(stmt, PaintNodesStmt_N):
                # get the name of the node-class
                node_class_ref = list(
                    stmt.rhs.get_referenced_symbols()
                )[0]  # get *single* element from set
                node_class_name = node_class_ref.name

                # check that the node-class has been defined @NodeClassesBlock_N
                if not node.node_classes.symbol_defs.contains(node_class_name):
                    raise GeLBExSymbolUnknown(node_class_ref)

            elif isinstance(stmt, BorderStmt_N):
                # validate both source and target node classes exist
                for ident in (stmt.source, stmt.target):
                    ref = list(ident.get_referenced_symbols())[0]
                    if not node.node_classes.symbol_defs.contains(ref.name):
                        raise GeLBExSymbolUnknown(ref)

            elif isinstance(stmt, ConditionalPaintStmt_N):
                # validate node class exists; the predicate's own symbols
                # (functions, constants, coordinates) are checked when the
                # symbol tables are built and when types are inferred
                nc_ref = list(stmt.node_class.get_referenced_symbols())[0]
                if not node.node_classes.symbol_defs.contains(nc_ref.name):
                    raise GeLBExSymbolUnknown(nc_ref)
