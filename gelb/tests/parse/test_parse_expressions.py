#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import assert_cst_equals, get_expression_parse_test_data


class TestExpressionParsing:
    """Consolidated tests for expression parsing (CST) across all expression types."""
    
    @pytest.mark.parametrize("category,test_name,test_string,expected", get_expression_parse_test_data())
    def test_expression_parsing(self, category, test_name, test_string, expected):
        """Test parsing for all expression types."""
        assert_cst_equals(test_string, expected, "expr")