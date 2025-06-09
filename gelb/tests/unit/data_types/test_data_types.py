#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import (
    assert_ast_equals, assert_cst_equals, 
    get_data_type_test_data, get_data_type_parse_test_data,
    get_scalar_cst_test_data
)


class TestDataTypeAST:
    """Consolidated tests for data type AST building (scalar and array types)."""
    
    @pytest.mark.parametrize("category,rule,test_string,expected", get_data_type_test_data())
    def test_data_type_ast(self, category, rule, test_string, expected):
        """Test AST building for all data types."""
        assert_ast_equals(test_string, expected, rule)


class TestDataTypeParsing:
    """Consolidated tests for data type parsing (CST)."""
    
    @pytest.mark.parametrize("data_type,expected", get_scalar_cst_test_data())
    def test_scalar_data_type_parsing(self, data_type, expected):
        """Test parsing of scalar data types."""
        assert_cst_equals(data_type, expected, "scalar_data_type")
    
    @pytest.mark.parametrize("category,rule,test_string,expected", get_data_type_parse_test_data())
    def test_array_data_type_parsing(self, category, rule, test_string, expected):
        """Test parsing of array data types."""
        assert_cst_equals(test_string, expected, rule)