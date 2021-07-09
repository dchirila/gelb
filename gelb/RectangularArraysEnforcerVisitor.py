#!/usr/bin/env python3

import click
from colorama import Fore, Style

from gelb.ASTBaseVisitor import ASTBaseVisitor
from gelb.ASTNodes import *
from gelb.SymbolDefinition import SymbolDefinition
from gelb.utils.exceptions import (
    GeLBExSymbolUnknown,
    GeLBExSymbolConstantRecursion,
    GeLBExIncorrectStagesOrdering, GeLBExSyntaxError
)


class RectangularArraysEnforcerVisitor(ASTBaseVisitor):
    """
    Concrete visitor for ensuring that all array-literals are rectangular.

    NOTEs:
    - GeLB DOES NOT support ragged arrays!
    - We overload the =visit= method of the base-class, to avoid having to
    define visitor-overloads for all node types (we only care about
    array-literal nodes here).
    """
    def visit(self, node, ast_root_node):
        for child in node.get_children():  # iterate over children
            if isinstance(child, Node_N):  # ensure child is GeLB AST Node
                if isinstance(child, ArrayLiteral_N):
                    # TODO special logic for array-literals (AFTER evaluating
                    # types)
                    type_first_element = type(child.value[0])
                    print(f"<<<DEBUG-2>>> child {type_first_element}")
                    for element in child.value:
                        self.visit(element, ast_root_node)
                else:
                    # normal logic, for other nodes
                    self.visit(child, ast_root_node)
