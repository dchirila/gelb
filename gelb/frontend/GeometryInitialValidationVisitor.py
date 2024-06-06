#!/usr/bin/env python3

from frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb_ast.ASTNodes import *
from utils.exceptions import (
    GeLBExSymbolUnknown,
)


class GeometryInitialValidationVisitor(ASTBaseVisitor):
    """
    Concrete visitor for initial validation of the GeometryBlock_N.

    The main concern at this stage is to ensure that all of the node-classes
    referenced within the GeometryBlock_N were previously defined
    (inside the NodeClassesBlock_N).
    """
    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        for paint_nodes_stmt in node.geometry.stmts:
            # get the name of the node-class
            node_class_ref = list(
                paint_nodes_stmt.rhs.get_referenced_symbols()
            )[0]  # get *single* element from set
            node_class_name = node_class_ref.name

            # check that the node-class has been defined @NodeClassesBlock_N
            if not node.node_classes.symbol_defs.contains(node_class_name):
                raise GeLBExSymbolUnknown(node_class_ref)
