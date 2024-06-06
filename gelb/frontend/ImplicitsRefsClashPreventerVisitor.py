#!/usr/bin/env python3

import click
from colorama import Fore

from frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb_ast.ASTNodes import *
from utils.exceptions import (
    GeLBExSymbolNotAllowedHere
)


class ImplicitsRefsClashPreventerVisitor(ASTBaseVisitor):
    """
    Concrete visitor for preventing clashes with implicit constants &variables.
    """
    def check_node_symbol_refs(self, node):
        for sref in node.get_referenced_symbols():
            self.check_ref_for_clashes(sref, node)

    def check_ref_for_clashes(self, ref, node):
        name = ref.name

        if name in ["x", "y", "z"]:
            if not (isinstance(node, InitializerBlock_N) or
                    isinstance(node, DynamicBlock_N) or
                    isinstance(node, GaugeBlock_N)):
                error = (
                    f"You are using the implicit variable"
                    f" {click.style(name, underline=True) + Fore.RED}"
                    f" (representing the {name}-coordinate of a lattice node)"
                    f" in a block where it does not make sense."
                )
                hint = (
                    f"{click.style(name, underline=True) + Fore.GREEN}"
                    f" may be used *only* inside initializers, dynamics &"
                    f" gauges blocks."
                )
                if name == "x":
                    hint += "."
                elif name == "y":
                    hint += " (and only for 2D & 3D simulations)."
                elif name == "z":
                    hint += " (and only for 3D simulations)."

                raise GeLBExSymbolNotAllowedHere(ref, error, hint)
            else:  # node is InitializerBlock_N, DynamicBlock_N or GaugeBlock_N
                for stmt in node.stmts:
                    # check refs in value-field @ConstantDefinitionStmt_N
                    if isinstance(stmt, ConstantDefinitionStmt_N):
                        error = (
                            f"You are using the implicit variable "
                            f"{click.style(name, underline=True) + Fore.RED}"
                            f" for initializing a constant."
                        )
                        hint = (
                            f"A constant can only be initialized with a"
                            f" constant value."
                        )
                        for sref in stmt.value.get_referenced_symbols():
                            raise GeLBExSymbolNotAllowedHere(sref, error, hint)
                    # check lhs @VariableAssignmentStmt_N (s.t. we don't
                    # overwrite the implicit variables x, y, z)
                    elif isinstance(stmt, VariableAssignmentStmt_N):
                        error = (
                            f"You are trying to overwrite the implicit variable"
                            f" {click.style(name, underline=True) + Fore.RED}"
                            f" (representing the {name}-coordinate of a lattice"
                            f" node)."
                        )
                        hint = (
                            f"{click.style(name, underline=True) + Fore.GREEN}"
                            f" is set automatically when each lattice node is"
                            f" processed. You are not allowed to write to it."
                        )
                        if name == stmt.lhs.name:
                            raise GeLBExSymbolNotAllowedHere(
                                stmt.lhs, error, hint
                            )
                    # NOTE: other parts of the code ensure that we don't try
                    # to define a variable called "x".
        elif (
                (name in ["Nx", "Ny", "Nz"]) and
                not (isinstance(node, PaintNodesStmt_N))
        ):
            error = (
                f"You are using the implicit constant"
                f" {click.style(name, underline=True) + Fore.RED}"
                f" (representing the size of the simulation domain"
                f" along the {name[-1]}-coordinate) in a place where it does"
                f" not make sense."
            )
            hint = (
                f"{click.style(name, underline=True) + Fore.GREEN}"
                f" may be used *only* inside the brackets of the"
                f" \"nodes[...]\" construct, inside the geometry block"
            )
            if name == "Nx":
                hint += "."
            elif name == "Ny":
                hint += " (and only for 2D & 3D simulations)."
            elif name == "Nz":
                hint += " (and only for 3D simulations)."

            raise GeLBExSymbolNotAllowedHere(ref, error, hint)

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

        # trigger check of symbol refs @Initializer_N blocks
        for initializer in node.initializers:
            self.visit(initializer, ast_root_node)

        # trigger check of symbol refs @Dynamic_N blocks
        for dynamic in node.dynamics:
            self.visit(dynamic, ast_root_node)

        # trigger check of symbol refs @Gauge_N blocks
        for gauge in node.gauges:
            self.visit(gauge, ast_root_node)

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

    def visitInitializerBlock_N(
            self,
            node: InitializerBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_refs(node)

    def visitDynamicBlock_N(
            self,
            node: DynamicBlock_N,
            ast_root_node: Program_N
    ):
        self.check_node_symbol_refs(node)

    def visitGaugeBlock_N(
            self,
            node: GaugeBlock_N,
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
        self.check_node_symbol_refs(node.grid_size)
        self.check_node_symbol_refs(node.grid_periodicity)
        for stmt in node.stmts:
            self.check_node_symbol_refs(stmt)
