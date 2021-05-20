#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = "simulation_name(\"test_1\");"
    ast_builder = ASTBuilderVisitor()
    # Act (trigger parsing & building of sub-AST)
    ast = get_ast("set_simulation_name_stmt", test_string)
    # Assert (test the (sub-)AST, based on string representation)
    assert str(ast) == "(StringLiteral \"test_1\")"


def test_with_comments():
    # Arrange
    test_string = "\n\n/*some comment*/simulation_name/*an other*/(\n\"test 2\");"
    ast_builder = ASTBuilderVisitor()
    # Act (trigger parsing & building of sub-AST)
    ast = get_ast("set_simulation_name_stmt", test_string)
    # Assert (test the (sub-)AST, based on string representation)
    assert str(ast) == "(StringLiteral \"test 2\")"
