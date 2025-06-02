#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import assert_ast_equals, get_range_test_data


class TestRangeAST:
    """Consolidated tests for range AST building (coordinate and lattice DF ranges)."""
    
    @pytest.mark.parametrize("category,rule,test_string,expected", get_range_test_data())
    def test_range_ast(self, category, rule, test_string, expected):
        """Test AST building for all range types."""
        assert_ast_equals(test_string, expected, rule)