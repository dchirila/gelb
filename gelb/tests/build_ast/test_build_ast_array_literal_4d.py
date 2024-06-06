#!/usr/bin/env python3

import pytest
from frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = (
        "{{{{1,2},{3,4}},{{5,6},{7,8}}},{{{9,10},{11,12}},{{13,14},{15,16}}}}"
    )
    # Act (trigger parsing & building of sub-AST)
    ast = get_ast("array_literal_4d", test_string)
    # Assert (test the (sub-)AST, based on string representation)
    assert str(ast) == (
        "(ArrayLiteral4D"
        " (ArrayLiteral3D"
            " (ArrayLiteral2D"
            " (ArrayLiteral1D (IntLiteral 1) (IntLiteral 2))"
            " (ArrayLiteral1D (IntLiteral 3) (IntLiteral 4))"
            ")"
            " (ArrayLiteral2D"
            " (ArrayLiteral1D (IntLiteral 5) (IntLiteral 6))"
            " (ArrayLiteral1D (IntLiteral 7) (IntLiteral 8))"
            ")"
        ")"
        " (ArrayLiteral3D"
            " (ArrayLiteral2D"
            " (ArrayLiteral1D (IntLiteral 9) (IntLiteral 10))"
            " (ArrayLiteral1D (IntLiteral 11) (IntLiteral 12))"
            ")"
            " (ArrayLiteral2D"
            " (ArrayLiteral1D (IntLiteral 13) (IntLiteral 14))"
            " (ArrayLiteral1D (IntLiteral 15) (IntLiteral 16))"
            ")"
        ")"
        ")"
    )