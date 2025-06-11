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
    simulation_description("Test lattice validation");
    lattices {{
        {lattices_content}
    }}
    initializer Init {{
        f.out[x | 0] = 0;
    }}
    dynamic Dyn {{
        f.out[x | 0] = 1;
    }}
    gauge Out(out = {{int val;}}) {{
        val = f.in[x | 0];
    }}
    node_classes {{
        node_class BULK(Init, Dyn, Out);
    }}
    geometry {{
        nodes[:] = BULK;
    }}
    """


class TestLatticeParameterValidation:
    """Test lattice instantiation parameter validation (d, q, grid_size)."""
    
    def test_valid_lattice_parameters_1d(self):
        """Test that valid 1D lattice parameters pass validation."""
        gelb_code = create_lattice_program("lattice f(1, 1, int, 32, false);")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_valid_lattice_parameters_2d(self):
        """Test that valid 2D lattice parameters pass validation."""
        gelb_code = create_lattice_program("lattice f(2, 9, int, {32, 64}, {true, false});")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_valid_lattice_parameters_3d(self):
        """Test that valid 3D lattice parameters pass validation."""
        gelb_code = create_lattice_program("lattice f(3, 19, int, {16, 32, 48}, {true, true, false});")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None


class TestDimensionalityValidation:
    """Test dimensionality (d) parameter validation."""
    
    def test_d_zero_invalid(self):
        """Test that d=0 is rejected."""
        gelb_code = create_lattice_program("lattice f(0, 1, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Lattice dimensionality d=0 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_d_negative_invalid(self):
        """Test that negative d is rejected."""
        gelb_code = create_lattice_program("lattice f(-1, 1, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Lattice dimensionality d=-1 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_d_four_invalid(self):
        """Test that d=4 is rejected (max is 3)."""
        gelb_code = create_lattice_program("lattice f(4, 1, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Lattice dimensionality d=4 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_d_large_invalid(self):
        """Test that large d values are rejected."""
        gelb_code = create_lattice_program("lattice f(100, 1, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Lattice dimensionality d=100 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    @pytest.mark.parametrize("d_value,grid_size,periodicity", [
        (1, "32", "false"),
        (2, "{32, 64}", "{false, true}"),
        (3, "{32, 64, 128}", "{false, true, false}")
    ])
    def test_d_valid_range(self, d_value, grid_size, periodicity):
        """Test that d=1,2,3 are all valid with appropriate grid_size/periodicity."""
        gelb_code = create_lattice_program(f"lattice f({d_value}, 1, int, {grid_size}, {periodicity});")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None


class TestDistributionFunctionsValidation:
    """Test number of distribution functions (q) parameter validation."""
    
    def test_q_zero_invalid(self):
        """Test that q=0 is rejected."""
        gelb_code = create_lattice_program("lattice f(1, 0, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Number of distribution functions q=0 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_q_negative_invalid(self):
        """Test that negative q is rejected."""
        gelb_code = create_lattice_program("lattice f(1, -5, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Number of distribution functions q=-5 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    @pytest.mark.parametrize("q_value", [1, 9, 19, 27, 100])
    def test_q_valid_values(self, q_value):
        """Test that positive q values are valid."""
        gelb_code = create_lattice_program(f"lattice f(1, {q_value}, int, 32, false);")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None


class TestGridSizeValidation:
    """Test grid size parameter validation."""
    
    def test_grid_size_zero_invalid(self):
        """Test that grid_size=0 is rejected."""
        gelb_code = create_lattice_program("lattice f(1, 1, int, 0, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size 0 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_grid_size_negative_invalid(self):
        """Test that negative grid_size is rejected."""
        gelb_code = create_lattice_program("lattice f(1, 1, int, -32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size -32 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_grid_size_array_negative_element_invalid(self):
        """Test that negative elements in grid_size array are rejected."""
        gelb_code = create_lattice_program("lattice f(2, 1, int, {32, -64}, {true, false});")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size element \[1\] = -64 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_grid_size_array_zero_element_invalid(self):
        """Test that zero elements in grid_size array are rejected."""
        gelb_code = create_lattice_program("lattice f(2, 1, int, {32, 0}, {true, false});")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size element \[1\] = 0 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_grid_size_array_multiple_invalid_elements(self):
        """Test validation catches first invalid element in grid_size array."""
        gelb_code = create_lattice_program("lattice f(3, 1, int, {-16, -32, -48}, {true, true, false});")
        
        # Should catch the first invalid element (index 0)
        with pytest.raises(GeLBExTypeError, match=r"Grid size element \[0\] = -16 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    @pytest.mark.parametrize("grid_size", [1, 16, 32, 64, 128, 1000])
    def test_grid_size_valid_values(self, grid_size):
        """Test that positive grid_size values are valid."""
        gelb_code = create_lattice_program(f"lattice f(1, 1, int, {grid_size}, false);")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_grid_size_array_valid_values(self):
        """Test that arrays with all positive grid_size values are valid."""
        gelb_code = create_lattice_program("lattice f(3, 1, int, {16, 32, 48}, {true, true, false});")
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None


class TestCombinedValidation:
    """Test combinations of invalid parameters."""
    
    def test_multiple_invalid_parameters_d_and_q(self):
        """Test that validation catches the first invalid parameter (d before q)."""
        gelb_code = create_lattice_program("lattice f(-1, 0, int, 32, false);")
        
        # Should catch d=-1 first
        with pytest.raises(GeLBExTypeError, match=r"Lattice dimensionality d=-1 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_multiple_invalid_parameters_q_and_grid_size(self):
        """Test validation with invalid q and grid_size (q checked first)."""
        gelb_code = create_lattice_program("lattice f(1, -5, int, -32, false);")
        
        # Should catch q=-5 first  
        with pytest.raises(GeLBExTypeError, match=r"Number of distribution functions q=-5 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_all_invalid_parameters(self):
        """Test validation with all parameters invalid (d checked first)."""
        gelb_code = create_lattice_program("lattice f(0, -1, int, -32, false);")
        
        # Should catch d=0 first
        with pytest.raises(GeLBExTypeError, match=r"Lattice dimensionality d=0 is invalid"):
            get_fully_validated_ast(gelb_code)


class TestUnaryMinusExpressionHandling:
    """Test that validation correctly handles UnaryMinusExpr_N nodes."""
    
    def test_unary_minus_d_validation(self):
        """Test that -1 as UnaryMinusExpr is correctly validated for d."""
        gelb_code = create_lattice_program("lattice f(-1, 1, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Lattice dimensionality d=-1 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_unary_minus_q_validation(self):
        """Test that -1 as UnaryMinusExpr is correctly validated for q."""
        gelb_code = create_lattice_program("lattice f(1, -1, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Number of distribution functions q=-1 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_unary_minus_grid_size_validation(self):
        """Test that -32 as UnaryMinusExpr is correctly validated for grid_size."""
        gelb_code = create_lattice_program("lattice f(1, 1, int, -32, false);")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size -32 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_unary_minus_in_grid_size_array(self):
        """Test that -values in grid_size array are correctly validated."""
        gelb_code = create_lattice_program("lattice f(2, 1, int, {-16, 32}, {true, false});")
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size element \[0\] = -16 is invalid"):
            get_fully_validated_ast(gelb_code)


class TestMultipleLatticesValidation:
    """Test validation works with multiple lattice instantiations."""
    
    def test_multiple_valid_lattices(self):
        """Test that multiple valid lattices pass validation."""
        gelb_code = create_lattice_program("""
                lattice f(1, 1, int, 32, false);
                lattice g(2, 9, int, {64, 128}, {true, false});
                lattice h(3, 19, int, {16, 32, 48}, {true, true, false});
            """)
        
        # Should not raise any exception
        ast = get_fully_validated_ast(gelb_code)
        assert ast is not None
    
    def test_multiple_lattices_one_invalid_d(self):
        """Test that validation catches invalid d in second lattice."""
        gelb_code = create_lattice_program("""
                lattice f(1, 1, int, 32, false);
                lattice g(4, 9, int, {64, 128}, {true, false});
                lattice h(3, 19, int, {16, 32, 48}, {true, true, false});
            """)
        
        with pytest.raises(GeLBExTypeError, match=r"Lattice dimensionality d=4 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_multiple_lattices_one_invalid_q(self):
        """Test that validation catches invalid q in third lattice."""
        gelb_code = create_lattice_program("""
                lattice f(1, 1, int, 32, false);
                lattice g(2, 9, int, {64, 128}, {true, false});
                lattice h(3, 0, int, {16, 32, 48}, {true, true, false});
            """)
        
        with pytest.raises(GeLBExTypeError, match=r"Number of distribution functions q=0 is invalid"):
            get_fully_validated_ast(gelb_code)
    
    def test_multiple_lattices_one_invalid_grid_size(self):
        """Test that validation catches invalid grid_size in first lattice."""
        gelb_code = create_lattice_program("""
                lattice f(1, 1, int, -32, false);
                lattice g(2, 9, int, {64, 128}, {true, false});
                lattice h(3, 19, int, {16, 32, 48}, {true, true, false});
            """)
        
        with pytest.raises(GeLBExTypeError, match=r"Grid size -32 is invalid"):
            get_fully_validated_ast(gelb_code)


class TestErrorMessages:
    """Test that error messages are clear and helpful."""
    
    def test_d_error_message_content(self):
        """Test that d validation error contains helpful guidance."""
        gelb_code = create_lattice_program("lattice f(5, 1, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Lattice dimensionality d=5 is invalid" in error_msg
        assert "Dimensionality must be between 1 and 3 (inclusive), got 5" in error_msg
    
    def test_q_error_message_content(self):
        """Test that q validation error contains helpful guidance."""
        gelb_code = create_lattice_program("lattice f(1, -3, int, 32, false);")
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Number of distribution functions q=-3 is invalid" in error_msg
        assert "Number of distribution functions must be positive, got -3" in error_msg
    
    def test_grid_size_error_message_content(self):
        """Test that grid_size validation error contains helpful guidance."""
        gelb_code = create_lattice_program("lattice f(1, 1, int, -64, false);")
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Grid size -64 is invalid" in error_msg
        assert "Grid size must be positive, got -64" in error_msg
    
    def test_grid_size_array_error_message_content(self):
        """Test that grid_size array validation error contains helpful guidance."""
        gelb_code = create_lattice_program("lattice f(2, 1, int, {32, -16}, {true, false});")
        
        with pytest.raises(GeLBExTypeError) as exc_info:
            get_fully_validated_ast(gelb_code)
        
        error_msg = str(exc_info.value)
        assert "Grid size element [1] = -16 is invalid" in error_msg
        assert "All grid size elements must be positive, got -16" in error_msg