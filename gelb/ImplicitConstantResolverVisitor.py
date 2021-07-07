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
        for lattice_insta in node.lattices.stmts:
            print(
                f"<<<DEBUG>>>"
                f" ID = {lattice_insta.name}"
                f" D = {lattice_insta.d}"
                f" Q = {lattice_insta.q}"
            )
        return node
