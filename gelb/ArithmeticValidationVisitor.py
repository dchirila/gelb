#!/usr/bin/env python3

from gelb.ASTBaseVisitor import ASTBaseVisitor


class ArithmeticValidationVisitor(ASTBaseVisitor):
    """
    Concrete visitor for validation of arithmetic expressions.
    TODO:
    - @visitDiv_N: check for division by zero
    """
    pass
