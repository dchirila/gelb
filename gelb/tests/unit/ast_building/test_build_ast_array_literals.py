#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import assert_ast_equals, get_array_literal_ast_test_data


class TestArrayLiteralAST:
    """Test AST building for array literals across all dimensions."""
    
    @pytest.mark.parametrize("dimension,test_name,test_string,expected", get_array_literal_ast_test_data())
    def test_array_literal_ast(self, dimension, test_name, test_string, expected):
        """Test AST building for array literals."""
        rule = f"array_literal_{dimension}"
        assert_ast_equals(test_string, expected, rule)