#!/usr/bin/env python3

import pytest
from gelb.tests.test_utils import assert_cst_equals, get_scalar_data_types


class TestScalarDataTypeParsing:
    """Test parsing of scalar data types."""
    
    @pytest.mark.parametrize("data_type,expected", get_scalar_data_types())
    def test_scalar_data_type(self, data_type, expected):
        """Test parsing of scalar data type."""
        assert_cst_equals(data_type, expected, "scalar_data_type")