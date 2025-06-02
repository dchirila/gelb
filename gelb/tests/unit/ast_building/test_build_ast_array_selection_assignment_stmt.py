#!/usr/bin/env python3

import pytest
from gelb.tests.unit.ast_building.ast_test_utils import assert_ast_equals, get_array_selection_assignment_ast_test_data


class TestArraySelectionAssignmentAST:
    """Consolidated tests for array selection assignment statement AST building."""
    
    @pytest.mark.parametrize("category,test_name,test_string,expected", get_array_selection_assignment_ast_test_data())
    def test_array_selection_assignment_ast(self, category, test_name, test_string, expected):
        """Test AST building for array selection assignment statements."""
        assert_ast_equals(test_string, expected, "array_selection_assignment_stmt")