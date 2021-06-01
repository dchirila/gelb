#!/usr/bin/env python3

import pytest
from gelb.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = """
    node_classes { //
      node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);
    }
    """
    # Act
    ast = get_ast("node_classes_block", test_string)
    # Assert
    assert str(ast) == (
        "(NodeClassesBlock"
        " (NodeClassInstaStmt"
            " (Identifier BULK)"
            " (Identifier SetDFsToZero)"
            " (Identifier SetDFsToOne)"
            " (Identifier CurrentState)"
            ")"
        ")"
    )
