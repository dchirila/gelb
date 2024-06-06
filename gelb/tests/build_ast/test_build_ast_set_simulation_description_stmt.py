#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = """
    simulation_description("test_1");
    """
    ast_builder = ASTBuilderVisitor()
    # Act (trigger parsing & building of sub-AST)
    ast = get_ast("set_simulation_description_stmt", test_string)
    # Assert (test the (sub-)AST, based on string representation)
    assert str(ast) == (
        "(SetSimulationDescriptionStmt (StringLiteral \"test_1\"))"
    )

def test_with_comments():
    # Arrange
    test_string = """
    
    
/*some comment*/simulation_description/*an other*/(
"test
 2");
    """
    ast_builder = ASTBuilderVisitor()
    # Act (trigger parsing & building of sub-AST)
    ast = get_ast("set_simulation_description_stmt", test_string)
    # Assert (test the (sub-)AST, based on string representation)
    assert str(ast) == (
        "(SetSimulationDescriptionStmt (StringLiteral \"test\n 2\"))"
    )
