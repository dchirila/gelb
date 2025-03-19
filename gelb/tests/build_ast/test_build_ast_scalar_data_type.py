#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_bool():
    # Arrange
    test_string = "bool"
    # Act
    ast = get_ast("scalar_data_type", test_string)
    # Assert
    assert str(ast) == "(ScalarDataType bool)"

def test_int64():
    # Arrange
    test_string = "int64"
    # Act
    ast = get_ast("scalar_data_type", test_string)
    # Assert
    assert str(ast) == "(ScalarDataType int64)"

def test_int32():
    # Arrange
    test_string = "int32"
    # Act
    ast = get_ast("scalar_data_type", test_string)
    # Assert
    assert str(ast) == "(ScalarDataType int32)"

def test_int16():
    # Arrange
    test_string = "int16"
    # Act
    ast = get_ast("scalar_data_type", test_string)
    # Assert
    assert str(ast) == "(ScalarDataType int16)"

def test_int8():
    # Arrange
    test_string = "int8"
    # Act
    ast = get_ast("scalar_data_type", test_string)
    # Assert
    assert str(ast) == "(ScalarDataType int8)"

def test_int():
    # Arrange
    test_string = "int"
    # Act
    ast = get_ast("scalar_data_type", test_string)
    # Assert
    assert str(ast) == "(ScalarDataType int)"

def test_real64():
    # Arrange
    test_string = "real64"
    # Act
    ast = get_ast("scalar_data_type", test_string)
    # Assert
    assert str(ast) == "(ScalarDataType real64)"

def test_real32():
    # Arrange
    test_string = "real32"
    # Act
    ast = get_ast("scalar_data_type", test_string)
    # Assert
    assert str(ast) == "(ScalarDataType real32)"

def test_real16():
    # Arrange
    test_string = "real16"
    # Act
    ast = get_ast("scalar_data_type", test_string)
    # Assert
    assert str(ast) == "(ScalarDataType real16)"

def test_real():
    # Arrange
    test_string = "real"
    # Act
    ast = get_ast("scalar_data_type", test_string)
    # Assert
    assert str(ast) == "(ScalarDataType real)"