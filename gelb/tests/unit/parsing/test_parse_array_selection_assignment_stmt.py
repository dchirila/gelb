#!/usr/bin/env python3

import pytest
from gelb.tests.unit.parsing.parsing_test_utils import assert_cst_equals, get_array_selection_assignment_parse_test_data


class TestParseArraySelectionAssignmentStatement:
    """Consolidated tests for array selection assignment statement parsing (CST)."""

    @pytest.mark.parametrize("category,test_name,test_string,expected", get_array_selection_assignment_parse_test_data())
    def test_array_selection_assignment_parsing(self, category, test_name, test_string, expected):
        """Test parsing for array selection assignment statements."""
        assert_cst_equals(test_string, expected, "array_selection_assignment_stmt")