#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import assert_cst_equals, get_array_literal_parse_test_data


class TestArrayLiteralParsing:
    """Test parsing of array literals across all dimensions."""
    
    @pytest.mark.parametrize("dimension,test_name,test_string,expected", get_array_literal_parse_test_data())
    def test_array_literal(self, dimension, test_name, test_string, expected):
        """Test parsing of array literals."""
        rule = f"array_literal_{dimension}"
        assert_cst_equals(test_string, expected, rule)