#!/usr/bin/env python3

import pytest
from gelb.tests.unit.parsing.parsing_test_utils import assert_cst_equals


class TestParseArraySelectionAssignmentStatement:
    """Test parsing of array selection assignment statements."""

    def test_simple_element_assignment(self):
        """Test simple element assignment: arr[0] = 42;"""
        test_string = "arr[0] = 42;"
        expected = (
            "(array_selection_assignment_stmt"
            " (rect_sel_of_array_elems"
            " (identifier arr)"
            " [ (coords_range (expr 0)) ]"
            ")"
            " = (expr 42) ;)"
        )
        assert_cst_equals(test_string, expected, "array_selection_assignment_stmt")

    def test_2d_assignment(self):
        """Test 2D array assignment: matrix[x, y] = value;"""
        test_string = "matrix[x, y] = value;"
        expected = (
            "(array_selection_assignment_stmt"
            " (rect_sel_of_array_elems"
            " (identifier matrix)"
            " [ (coords_range (expr (identifier x))) , (coords_range (expr (identifier y))) ]"
            ")"
            " = (expr (identifier value)) ;)"
        )
        assert_cst_equals(test_string, expected, "array_selection_assignment_stmt")

    def test_slice_assignment(self):
        """Test slice assignment: arr[1:3] = expr;"""
        test_string = "arr[1:3] = expr;"
        expected = (
            "(array_selection_assignment_stmt"
            " (rect_sel_of_array_elems"
            " (identifier arr)"
            " [ (coords_range (expr 1) : (expr 3)) ]"
            ")"
            " = (expr (identifier expr)) ;)"
        )
        assert_cst_equals(test_string, expected, "array_selection_assignment_stmt")