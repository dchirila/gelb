#!/usr/bin/env python3

import click
from colorama import Fore

from frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb_ast.ASTNodes import *
from utils.exceptions import (
    GeLBExSyntaxError
)


class ImplicitsDefsClashPreventerVisitor(ASTBaseVisitor):
    """
    Concrete visitor for preventing clashes with implicit constants &variables.
    """
    def __init__(self):
        # generic error-message
        self.error = "Your GeLB program contains a syntax error."
        self.hint_suffix = f" Please choose another identifier."

    def check_node_symbol_table(self, node):
        if node.symbol_defs is not None:
            for symbol_def in node.symbol_defs:
                self.check_id_for_clashes(symbol_def.value)

    def check_id_for_clashes(self, identifier):
        line = identifier.name.code_range.start_line
        column = identifier.name.code_range.start_col
        name = identifier.name.name
        if name in ["x", "y", "z"]:
            hint_prefix = (
                f"You cannot use"
                f" {click.style(name, underline=True) + Fore.GREEN}"
                f" as an identifier, because it is an implicit "
            )
            raise GeLBExSyntaxError(
                line, column,
                self.error,
                hint=(
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
                hint=(
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
        self.check_node_symbol_table(node)
        # trigger check of symbols table of GlobalConstantsBlock_N
        if node.global_constants is not None:
            self.visit(node.global_constants, ast_root_node)
        # trigger check of symbols table @LatticesBlock_N
        self.visit(node.lattices, ast_root_node)
        # trigger check of symbols table @initializers
        for initializer in node.initializers:
            self.visit(initializer, ast_root_node)
        # trigger check of symbols table @dynamics
        for dynamic in node.dynamics:
            self.visit(dynamic, ast_root_node)
        # trigger check of symbols table @gauges
        for gauge in node.gauges:
            self.visit(gauge, ast_root_node)
        # trigger check of symbols table @NodeClassesBlock_N
        self.visit(node.node_classes, ast_root_node)
        # trigger check of symbols table @GeometryBlock_N
        # TODO: ATM, there is no symbol_defs @GeometryBlock_N, but we will
        # probably add support for them in later releases of GeLB (in which
        # case this code should just work).
        self.visit(node.geometry, ast_root_node)

    def visitGlobalConstantsBlock_N(
            self,
            node: GlobalConstantsBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_table(node)

    def visitLatticesBlock_N(
            self,
            node: LatticesBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_table(node)

    def visitInitializerBlock_N(
            self,
            node: InitializerBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_table(node)

    def visitDynamicBlock_N(
            self,
            node: DynamicBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_table(node)

    def visitGaugeBlock_N(
            self,
            node: GaugeBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_table(node)

    def visitNodeClassesBlock_N(
            self,
            node: NodeClassesBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_table(node)

    def visitGeometryBlock_N(
            self,
            node: GeometryBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_table(node)
