#!/usr/bin/env python3

import click
from colorama import Fore

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.implicit_symbols import (
    DIMENSION_CONSTANT_NAMES,
    RUNTIME_IMPLICIT_SYMBOL_NAMES,
    TIMESTEP_SYMBOL_NAME,
    allows_predicate_coordinates,
    allows_runtime_coordinates,
)
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import (
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

        if name in RUNTIME_IMPLICIT_SYMBOL_NAMES:
            if allows_predicate_coordinates(node):
                if name == TIMESTEP_SYMBOL_NAME:
                    # The geometry is fixed for the whole run in this
                    # version; say so, instead of "unknown symbol".
                    raise GeLBExSymbolNotAllowedHere(
                        ref,
                        f"The geometry block refers to the time step"
                        f" {click.style(name, underline=True) + Fore.RED},"
                        f" but time-dependent geometry is not supported"
                        f" in this version of GeLB.",
                        "In this version the geometry is fixed for the"
                        " whole run: a paint predicate may use only the"
                        " coordinates (x, y, z), constants and pure"
                        " functions of them.",
                    )
                # Coordinates are predicate inputs here.  Their misuse in
                # a range or point paint is reported, with the right
                # message, by GeometryDependencyValidator.
                return
            if not allows_runtime_coordinates(node):
                if name == TIMESTEP_SYMBOL_NAME:
                    error = (
                        f"You are using the implicit variable"
                        f" {click.style(name, underline=True) + Fore.RED}"
                        f" (representing the current outer-loop iteration"
                        f" index) in a block where it does not make sense."
                    )
                else:
                    error = (
                        f"You are using the implicit variable"
                        f" {click.style(name, underline=True) + Fore.RED}"
                        f" (representing the {name}-coordinate of a lattice"
                        f" node) in a block where it does not make sense."
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
        elif name in DIMENSION_CONSTANT_NAMES:
            # Nx, Ny, Nz are implicit dimension constants that are added later in the pipeline.
            # At this point in compilation (before add_implicit_symbols), they don't exist yet,
            # so references to them should be invalid except in specific contexts.
            if isinstance(node, GlobalConstantsBlock_N):
                # Invalid: global constants are processed before implicit symbols are added
                error = (
                    f"You are using the implicit constant"
                    f" {click.style(name, underline=True) + Fore.RED}"
                    f" (representing the size of the simulation domain"
                    f" along the {name[-1]}-coordinate) in a global constants block."
                )
                hint = (
                    f"Global constants are processed before implicit constants like"
                    f" {click.style(name, underline=True) + Fore.GREEN}"
                    f" are available. Use explicit constants instead."
                )
                raise GeLBExSymbolNotAllowedHere(ref, error, hint)
            elif isinstance(node, LatticesBlock_N):
                # Invalid: lattice parameters are processed before implicit symbols are added
                error = (
                    f"You are using the implicit constant"
                    f" {click.style(name, underline=True) + Fore.RED}"
                    f" in lattice parameter expressions."
                )
                hint = (
                    f"Lattice parameters are processed before implicit constants like"
                    f" {click.style(name, underline=True) + Fore.GREEN}"
                    f" are available. Use explicit constants for lattice dimensions."
                )
                raise GeLBExSymbolNotAllowedHere(ref, error, hint)
            elif isinstance(node, NodeClassesBlock_N):
                # Invalid: node classes are processed before implicit symbols are added
                error = (
                    f"You are using the implicit constant"
                    f" {click.style(name, underline=True) + Fore.RED}"
                    f" in node classes block."
                )
                hint = (
                    f"Node classes are processed before implicit constants like"
                    f" {click.style(name, underline=True) + Fore.GREEN}"
                    f" are available."
                )
                raise GeLBExSymbolNotAllowedHere(ref, error, hint)
            # Note: GeometryBlock_N should allow Nx, Ny, Nz since geometry is processed 
            # after implicit symbols are conceptually available

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
        # Geometry block no longer has grid_size and grid_periodicity
        # These are now part of lattice instantiation statements.
        # The block, not the statement, decides what is allowed: the
        # coordinates are legal inside `where` predicates here.
        for stmt in node.stmts:
            for sref in stmt.get_referenced_symbols():
                self.check_ref_for_clashes(sref, node)
