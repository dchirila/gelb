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


class ImplicitConstantResolverVisitor(ASTBaseVisitor):
    """
    Concrete visitor for resolving the implicit constants for the simulation.

    Specifically, we resolve:
    - D ~> the dimensionality of the simulation
    - Q ~> the number of DFs of each lattice
    - Nx ~> size of the simulation domain along the X axis
    - [optional, if D>1] Ny ~> size of the simulation domain along the Y axis
    - [optional, if D>2] Nz ~> size of the simulation domain along the Z axis
    """
    def visitProgram_N(
            self,
            node: Program_N,
            ast_root_node: Program_N
    ):
        # generic error-message
        error = "Your GeLB program contains a syntax error."
        for lattice_insta in node.lattices.stmts:
            name = lattice_insta.name.name
            hint_suffix = f" Please choose another identifier."
            line = lattice_insta.name.code_range.start_line
            column = lattice_insta.name.code_range.start_col
            if name in ["x", "y", "z"]:
                hint_prefix = (
                    f"You cannot use"
                    f" {click.style(name, underline=True) + Fore.GREEN}"
                    f" as an identifier, because it is an implicit "
                )
                raise GeLBExSyntaxError(
                    line, column,
                    error,
                    hint = (
                        hint_prefix +
                        f"variable"
                        f" (representing the {name}-coordinate of lattice "
                        f"nodes, inside initializers, dynamics & gauges)." +
                        hint_suffix
                    )
                )
            print(type(lattice_insta.name.name))
            print(
                f"<<<DEBUG>>>"
                f" ID = {lattice_insta.name}"
                f" D = {lattice_insta.d}"
                f" Q = {lattice_insta.q}"
            )
        return node
