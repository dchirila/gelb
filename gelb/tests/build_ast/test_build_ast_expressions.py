#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import assert_ast_equals, get_expression_ast_test_data


class TestExpressionAST:
    """Consolidated tests for expression AST building across all expression types."""
    
    @pytest.mark.parametrize("category,test_name,test_string,expected", get_expression_ast_test_data())
    def test_expression_ast(self, category, test_name, test_string, expected):
        """Test AST building for all expression types."""
        assert_ast_equals(test_string, expected, "expr")