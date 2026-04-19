#!/usr/bin/env python3

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import (
    GeLBExSymbolUnknown,
    GeLBExSymbolWrongType
)


class NodeClassesValidationVisitor(ASTBaseVisitor):
    """
    Concrete visitor for validating the NodeClassesBlock_N.

    In particular, we want to ensure that all of the referenced {initializer,
    dynamic,gauge}s are defined elsewhere in the program.
    """
    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        for node_class_insta in node.node_classes.stmts:
            # check that name of initializer is in the program's global
            # symbols table (optional for masked node classes)
            if node_class_insta.initializer is not None:
                initializer_name = node_class_insta.initializer.name
                if not node.symbol_defs.contains(initializer_name):
                    raise GeLBExSymbolUnknown(node_class_insta.initializer)
                elif node.symbol_defs.get_symbol_definition(
                    initializer_name
                ).tag != "initializer":
                    raise GeLBExSymbolWrongType(
                        node_class_insta.initializer,
                        "initializer"
                    )
            # check that name of dynamic is in the program's global
            # symbols table (dynamic is optional -- None means static node)
            if node_class_insta.dynamic is not None:
                dynamic_name = node_class_insta.dynamic.name
                if not node.symbol_defs.contains(dynamic_name):
                    raise GeLBExSymbolUnknown(node_class_insta.dynamic)
                elif node.symbol_defs.get_symbol_definition(
                        dynamic_name
                ).tag != "dynamic":
                    raise GeLBExSymbolWrongType(
                        node_class_insta.dynamic,
                        "dynamic"
                    )
            # check that name of gauge is in the program's global
            # symbols table (None for masked node classes)
            if node_class_insta.gauge is not None:
                gauge_name = node_class_insta.gauge.name
                if not node.symbol_defs.contains(gauge_name):
                    raise GeLBExSymbolUnknown(node_class_insta.gauge)
                elif node.symbol_defs.get_symbol_definition(
                        gauge_name
                ).tag != "gauge":
                    raise GeLBExSymbolWrongType(
                        node_class_insta.gauge,
                        "gauge"
                    )
