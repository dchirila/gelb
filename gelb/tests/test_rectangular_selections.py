#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import assert_ast_equals, get_rectangular_selection_test_data


class TestRectangularSelectionAST:
    """Consolidated tests for rectangular selection AST building (array, lattice in/out)."""
    
    @pytest.mark.parametrize("category,rule,test_string,expected", get_rectangular_selection_test_data())
    def test_rectangular_selection_ast(self, category, rule, test_string, expected):
        """Test AST building for all rectangular selection types."""
        assert_ast_equals(test_string, expected, rule)