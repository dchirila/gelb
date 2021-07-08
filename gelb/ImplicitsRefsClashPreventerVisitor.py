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


class ImplicitsRefsClashPreventerVisitor(ASTBaseVisitor):
    """
    Concrete visitor for preventing clashes with implicit constants &variables.
    """
    def __init__(self):
        # generic error-message
        self.error = "Your GeLB program contains a syntax error."
        self.hint_suffix = (
            f" This block is not executed for specific lattice nodes,"
            f" so x, y & z don't make sense here. "
        )

    def check_node_symbol_refs(self, node):
        for sref in node.get_referenced_symbols():
            self.check_ref_for_clashes(sref)

    def check_ref_for_clashes(self, ref):
        line = ref.code_range.start_line
        column = ref.code_range.start_col
        name = ref.name
        if name in ["x", "y", "z"]:
            hint_prefix = (
                f"You may not refer to"
                f" {click.style(name, underline=True) + Fore.GREEN}"
                f" here, because it is an implicit "
            )
            raise GeLBExSyntaxError(
                line, column,
                self.error,
                hint = (
                        hint_prefix +
                        f"variable"
                        f" (representing the {name}-coordinate of lattice "
                        f"nodes, inside initializers, dynamics & gauges)." +
                        self.hint_suffix
                )
            )
        elif name in ["Nx", "Ny", "Nz"]:
            hint_prefix = (
                f"You cannot use"
                f" {click.style(name, underline=True) + Fore.GREEN}"
                f" as an identifier, because it is an implicit "
            )
            raise GeLBExSyntaxError(
                line, column,
                self.error,
                hint = (
                        hint_prefix +
                        f"constant"
                        f" (representing the size of the simulation domain "
                        f"along the {name[-1]}-coordinate)." +
                        self.hint_suffix
                )
            )

    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        # trigger check of symbol refs @GlobalConstantsBlock_N
        if node.global_constants is not None:
            self.visit(node.global_constants, ast_root_node)
        # trigger check of symbol refs @LatticesBlock_N
        self.visit(node.lattices, ast_root_node)
        # trigger check of symbol refs @NodeClassesBlock_N
        self.visit(node.node_classes, ast_root_node)
        # trigger check of symbol refs @GeometryBlock_N
        self.visit(node.geometry, ast_root_node)

    def visitGlobalConstantsBlock_N(
            self,
            node: GlobalConstantsBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_refs(node)

    def visitLatticesBlock_N(
            self,
            node: LatticesBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_refs(node)

    def visitNodeClassesBlock_N(
            self,
            node: NodeClassesBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_refs(node)

    def visitGeometryBlock_N(
            self,
            node: GeometryBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_refs(node)
