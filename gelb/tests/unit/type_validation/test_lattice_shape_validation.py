#!/usr/bin/env python3

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.utils.exceptions import GeLBExTypeError
from gelb.tests.test_utils import get_typed_ast, get_fully_validated_ast


def create_lattice_program(lattices_content):
    """
    Create a minimal GeLB program with custom lattice definition.
    
    Args:
        lattices_content (str): Content for the lattices block
        
    Returns:
        str: Complete GeLB program source code
    """
    return f"""
    simulation_description("Test lattice shape validation");
    lattices {{
        {lattices_content}
    }}
    initializer Init {{
        f.out[x | 0] = 0;
    }}
    dynamic Dyn {{
        f.out[x | 0] = 1;
    }}
    gauge Out -> (int val) {{
        val = f.in[x | 0];
    }}
    node_classes {{
        node_class BULK(Init, Dyn, Out);
    }}
    geometry {{
        nodes[:] = BULK;
    }}
    """


class TestGridSizeShapeValidation:
    """Test that grid_size shape matches dimensionality d."""
    
    def test_d1_scalar_grid_size_valid(self):
        """Test d=1 with scalar grid_size is valid."""
        gelb_code = create_lattice_program("lattice f(1, 1, int, 32, false);")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_d1_single_element_array_grid_size_valid(self):
        """Test d=1 with single-element array grid_size is valid."""
        # Note: GeLB grammar requires at least 2 elements in array literals
        # So we'll skip this test as single-element arrays aren't supported
        pytest.skip("Single-element array literals not supported by GeLB grammar")
    
    def test_d1_two_element_array_grid_size_invalid(self):
        """Test d=1 with 2-element array grid_size is invalid."""
        gelb_code = create_lattice_program("lattice f(1, 1, int, {32, 64}, {false, true});")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size has 2 elements but d=1"):
            get_fully_validated_ast(gelb_code)
    
    def test_d1_three_element_array_grid_size_invalid(self):
        """Test d=1 with 3-element array grid_size is invalid."""
        gelb_code = create_lattice_program("lattice f(1, 1, int, {32, 64, 128}, {false, true, false});")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size has 3 elements but d=1"):
            get_fully_validated_ast(gelb_code)
    
    def test_d2_scalar_grid_size_invalid(self):
        """Test d=2 with scalar grid_size is invalid."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size scalar is invalid for d=2"):
            get_fully_validated_ast(gelb_code)
    
    def test_d2_two_element_array_grid_size_valid(self):
        """Test d=2 with 2-element array grid_size is valid."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, {32, 64}, {false, true});")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_d2_one_element_array_grid_size_invalid(self):
        """Test d=2 with 1-element array grid_size is invalid."""
        # Note: GeLB grammar requires at least 2 elements in array literals
        # So we'll skip this test as single-element arrays aren't supported
        pytest.skip("Single-element array literals not supported by GeLB grammar")
    
    def test_d2_three_element_array_grid_size_invalid(self):
        """Test d=2 with 3-element array grid_size is invalid."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, {32, 64, 128}, {false, true, false});")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size has 3 elements but d=2"):
            get_fully_validated_ast(gelb_code)
    
    def test_d3_scalar_grid_size_invalid(self):
        """Test d=3 with scalar grid_size is invalid."""
        gelb_code = create_lattice_program("lattice f(3, 27, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size scalar is invalid for d=3"):
            get_fully_validated_ast(gelb_code)
    
    def test_d3_three_element_array_grid_size_valid(self):
        """Test d=3 with 3-element array grid_size is valid."""
        gelb_code = create_lattice_program("lattice f(3, 27, int, {32, 64, 128}, {false, true, false});")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_d3_two_element_array_grid_size_invalid(self):
        """Test d=3 with 2-element array grid_size is invalid."""
        gelb_code = create_lattice_program("lattice f(3, 27, int, {32, 64}, {false, true});")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size has 2 elements but d=3"):
            get_fully_validated_ast(gelb_code)


class TestPeriodicityShapeValidation:
    """Test that periodicity shape matches grid_size shape."""
    
    def test_scalar_grid_scalar_periodicity_valid(self):
        """Test scalar grid_size with scalar periodicity is valid."""
        gelb_code = create_lattice_program("lattice f(1, 1, int, 32, false);")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_scalar_grid_array_periodicity_invalid(self):
        """Test scalar grid_size with array periodicity is invalid."""
        # Note: GeLB grammar requires at least 2 elements in array literals
        # So we'll skip this test as single-element arrays aren't supported
        pytest.skip("Single-element array literals not supported by GeLB grammar")
    
    def test_array_grid_scalar_periodicity_invalid(self):
        """Test array grid_size with scalar periodicity is invalid."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, {32, 64}, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Periodicity is scalar but grid_size has 2 elements"):
            get_fully_validated_ast(gelb_code)
    
    def test_array_grid_matching_array_periodicity_valid(self):
        """Test array grid_size with matching array periodicity is valid."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, {32, 64}, {false, true});")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_array_grid_mismatched_array_periodicity_invalid(self):
        """Test array grid_size with mismatched array periodicity is invalid."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, {32, 64}, {false, true, false});")
        
        with pytest.raises(GeLBExTypeError, match=r"Periodicity has 3 elements but grid_size has 2"):
            get_fully_validated_ast(gelb_code)
    
    def test_1d_array_both_valid(self):
        """Test 1D with array grid_size and array periodicity is valid."""
        # Note: GeLB grammar requires at least 2 elements in array literals
        # So we'll skip this test as single-element arrays aren't supported
        pytest.skip("Single-element array literals not supported by GeLB grammar")
    
    def test_3d_array_both_valid(self):
        """Test 3D with array grid_size and array periodicity is valid."""
        gelb_code = create_lattice_program("lattice f(3, 27, int, {32, 64, 128}, {false, true, false});")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None


class TestCombinedShapeValidation:
    """Test combinations of shape mismatches."""
    
    def test_d_grid_size_mismatch_checked_first(self):
        """Test that d/grid_size mismatch is caught before periodicity mismatch."""
        # d=1 but grid_size has 2 elements, periodicity has 3 elements
        gelb_code = create_lattice_program("lattice f(1, 1, int, {32, 64}, {false, true, false});")
        
        # Should catch grid_size mismatch first
        with pytest.raises(GeLBExTypeError, match=r"Grid size has 2 elements but d=1"):
            get_fully_validated_ast(gelb_code)
    
    def test_original_issue_from_example_file(self):
        """Test the original issue from ex0_int_vec_setto_one.gelb."""
        # d=1, grid_size={32, 64} (2 elements), periodicity=false (scalar)
        gelb_code = create_lattice_program("lattice f(1, 1, int, {32, 64}, false);")
        
        # Should catch grid_size mismatch with d first
        with pytest.raises(GeLBExTypeError, match=r"Grid size has 2 elements but d=1"):
            get_fully_validated_ast(gelb_code)
    
    def test_all_parameters_consistent_2d(self):
        """Test that all parameters can be consistent for 2D."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, {32, 64}, {false, true});")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_shape_mismatch_reported_before_element_sign(self):
        """The rank of grid_size is validated at the declaration, before
        the element values are known, so a wrong rank wins over a negative
        element."""
        # d=2 but grid_size has 3 elements (shape mismatch) and one is negative
        gelb_code = create_lattice_program("lattice f(2, 9, int, {32, -64, 128}, {false, true, false});")

        with pytest.raises(GeLBExTypeError, match=r"Grid size has 3 elements but d=2"):
            get_fully_validated_ast(gelb_code)

    def test_negative_element_reported_when_rank_matches(self):
        """With the rank right, a negative element is still reported."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, {32, -64}, {false, true});")

        with pytest.raises(GeLBExTypeError, match=r"Grid size element \[1\] = -64 is invalid"):
            get_fully_validated_ast(gelb_code)


class TestErrorMessageQuality:
    """Test that error messages are clear and helpful for shape mismatches."""
    
    def test_grid_size_shape_error_message(self):
        """Test grid_size shape error message quality."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Grid size scalar is invalid for d=2" in error_msg
        assert "For d=2, grid_size must be a 2-element array, not a scalar" in error_msg
    
    def test_periodicity_shape_error_message_scalar_grid(self):
        """Test periodicity shape error message when grid is scalar."""
        # Note: GeLB grammar requires at least 2 elements in array literals
        # So we'll skip this test as single-element arrays aren't supported
        pytest.skip("Single-element array literals not supported by GeLB grammar")
    
    def test_periodicity_shape_error_message_array_grid(self):
        """Test periodicity shape error message when grid is array."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, {32, 64}, false);")
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Periodicity is scalar but grid_size has 2 elements" in error_msg
        assert "Periodicity must be a 2-element boolean array to match grid_size" in error_msg
    
    def test_periodicity_length_error_message(self):
        """Test periodicity length mismatch error message."""
        gelb_code = create_lattice_program("lattice f(3, 27, int, {32, 64, 128}, {false, true});")
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Periodicity has 2 elements but grid_size has 3" in error_msg
        assert "Periodicity must have exactly 3 elements to match grid_size" in error_msg


class TestMultipleLatticesShapeValidation:
    """Test shape validation with multiple lattices."""
    
    def test_multiple_lattices_all_valid_shapes(self):
        """Test multiple lattices with all valid shapes."""
        gelb_code = create_lattice_program("""
            lattice f(1, 1, int, 32, false);
            lattice g(2, 9, int, {64, 128}, {true, false});
            lattice h(3, 19, int, {16, 32, 48}, {true, true, false});
        """)
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_multiple_lattices_second_has_shape_mismatch(self):
        """Test that shape mismatch in second lattice is caught."""
        gelb_code = create_lattice_program("""
            lattice f(1, 1, int, 32, false);
            lattice g(2, 9, int, 64, false);
            lattice h(3, 19, int, {16, 32, 48}, {true, true, false});
        """)
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size scalar is invalid for d=2"):
            get_fully_validated_ast(gelb_code)
    
    def test_multiple_lattices_third_has_periodicity_mismatch(self):
        """Test that periodicity mismatch in third lattice is caught."""
        gelb_code = create_lattice_program("""
            lattice f(1, 1, int, 32, false);
            lattice g(2, 9, int, {64, 128}, {true, false});
            lattice h(3, 19, int, {16, 32, 48}, {true, false});
        """)
        
        with pytest.raises(GeLBExTypeError, match=r"Periodicity has 2 elements but grid_size has 3"):
            get_fully_validated_ast(gelb_code)


class TestValidShapeCombinations:
    """Test all valid shape combinations to ensure we don't over-restrict."""
    
    def test_1d_scalar_scalar(self):
        """Test 1D with scalar grid_size and scalar periodicity."""
        gelb_code = create_lattice_program("lattice f(1, 1, int, 32, false);")
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_1d_array_array(self):
        """Test 1D with 1-element array grid_size and periodicity."""
        # Note: GeLB grammar requires at least 2 elements in array literals
        # So we'll skip this test as single-element arrays aren't supported
        pytest.skip("Single-element array literals not supported by GeLB grammar")
    
    def test_2d_array_array(self):
        """Test 2D with 2-element array grid_size and periodicity."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, {32, 64}, {false, true});")
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_3d_array_array(self):
        """Test 3D with 3-element array grid_size and periodicity."""
        gelb_code = create_lattice_program("lattice f(3, 27, int, {32, 64, 128}, {false, true, false});")
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_mixed_boolean_values_in_periodicity(self):
        """Test various boolean combinations in periodicity arrays."""
        # All false
        gelb_code1 = create_lattice_program("lattice f(3, 27, int, {32, 64, 128}, {false, false, false});")
        ast1 = get_fully_validated_ast(gelb_code1)
        assert ast1 is not None
        
        # All true
        gelb_code2 = create_lattice_program("lattice f(3, 27, int, {32, 64, 128}, {true, true, true});")
        ast2 = get_fully_validated_ast(gelb_code2)
        assert ast2 is not None
        
        # Mixed
        gelb_code3 = create_lattice_program("lattice f(3, 27, int, {32, 64, 128}, {true, false, true});")
        ast3 = get_fully_validated_ast(gelb_code3)
        assert ast3 is not None