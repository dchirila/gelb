#!/usr/bin/env python3
"""
Comprehensive tests for lattice selection type inference with ArrayDataType_N system.

These tests validate that lattice selections (f.in[...], f.out[...]) correctly
infer array types with appropriate shapes based on selection patterns.
"""

from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import get_typed_ast


def real_lattice_program_1d(initializer_content="", dynamic_content=""):
    """Create a 1D program with real DF type for testing."""
    return f"""
simulation_description("Test");
lattices {{
    lattice f(1, 3, real, 32, false);
}}
initializer Init {{
    {initializer_content or "f.out[x|0] = 0.0;"}
}}
dynamic Dyn {{
    {dynamic_content or "f.out[x|0] = f.in[x|0];"}
}}
gauge Out(out = {{real val;}}) {{
    val = f.in[x|0];
}}
node_classes {{
    node_class BULK(Init, Dyn, Out);
}}
geometry {{
    nodes[:] = BULK;
}}
"""


def real_lattice_program_2d(initializer_content="", dynamic_content=""):
    """Create a 2D program with real DF type for testing."""
    return f"""
simulation_description("Test");
lattices {{
    lattice f(2, 9, real, {{32, 32}}, {{false, false}});
}}
initializer Init {{
    {initializer_content or "f.out[x,y|0] = 0.0;"}
}}
dynamic Dyn {{
    {dynamic_content or "f.out[x,y|0] = f.in[x,y|0];"}
}}
gauge Out(out = {{real val;}}) {{
    val = f.in[x,y|0];
}}
node_classes {{
    node_class BULK(Init, Dyn, Out);
}}
geometry {{
    nodes[:,:] = BULK;
}}
"""


class TestLatticeSelectionBasicTypeInference:
    """Test basic lattice selection type inference with ArrayDataType_N."""
    
    def test_lattice_in_selection_uses_array_types(self):
        """Lattice IN selections should use ArrayDataType_N consistently."""
        gelb_code = real_lattice_program_1d(
            initializer_content="f.out[x|:] = f.in[x|:];"
        )
        ast = get_typed_ast(gelb_code)
        
        # Navigate to the initializer block and find the assignment
        initializer = ast.initializers.elements[0]
        assignment = initializer.stmts.elements[0]
        
        # Get the lattice IN selection (RHS of assignment)
        lattice_in_sel = assignment.rhs
        
        assert isinstance(lattice_in_sel, RectSelOfLatticeInDFs_N)
        assert hasattr(lattice_in_sel, 'inferred_type')
        assert isinstance(lattice_in_sel.inferred_type, ArrayDataType_N)
        assert lattice_in_sel.inferred_type.scalar_dtype == "real"
    
    def test_lattice_out_selection_uses_array_types(self):
        """Lattice OUT selections should use ArrayDataType_N consistently."""
        gelb_code = real_lattice_program_1d(
            initializer_content="f.out[x|:] = 1.0;"
        )
        ast = get_typed_ast(gelb_code)
        
        # Navigate to the initializer block and find the assignment
        initializer = ast.initializers.elements[0]
        assignment = initializer.stmts.elements[0]
        
        # Get the lattice OUT selection (LHS of assignment)
        lattice_out_sel = assignment.lhs
        
        assert isinstance(lattice_out_sel, RectSelOfLatticeOutDFs_N)
        assert hasattr(lattice_out_sel, 'inferred_type')
        assert isinstance(lattice_out_sel.inferred_type, ArrayDataType_N)
        assert lattice_out_sel.inferred_type.scalar_dtype == "real"


class TestLatticeSelectionShapeInference:
    """Test that lattice selections correctly infer array shapes."""
    
    def test_full_df_selection_1d_infers_vector_shape(self):
        """Full DF selection f.in[x|:] should infer 1D array shape."""
        gelb_code = real_lattice_program_1d(
            initializer_content="f.out[x|:] = f.in[x|:];"
        )
        ast = get_typed_ast(gelb_code)
        
        # Get the lattice IN selection
        initializer = ast.initializers.elements[0]
        assignment = initializer.stmts.elements[0]
        lattice_in_sel = assignment.rhs
        
        inferred_type = lattice_in_sel.inferred_type
        assert isinstance(inferred_type, ArrayDataType_N)
        assert inferred_type.scalar_dtype == "real"
        
        # Should be 1D array (vector of DFs)
        assert len(inferred_type.shape.elements) == 1
        shape_element = inferred_type.shape.elements[0]
        assert isinstance(shape_element, Identifier_N)
        assert shape_element.name == "q"
    
    def test_full_df_selection_2d_infers_vector_shape(self):
        """Full DF selection f.in[x,y|:] should infer 1D array shape."""
        gelb_code = real_lattice_program_2d(
            initializer_content="f.out[x,y|:] = f.in[x,y|:];"
        )
        ast = get_typed_ast(gelb_code)
        
        # Get the lattice IN selection
        initializer = ast.initializers.elements[0]
        assignment = initializer.stmts.elements[0]
        lattice_in_sel = assignment.rhs
        
        inferred_type = lattice_in_sel.inferred_type
        assert isinstance(inferred_type, ArrayDataType_N)
        assert inferred_type.scalar_dtype == "real"
        
        # Should be 1D array (vector of DFs)
        assert len(inferred_type.shape.elements) == 1
        shape_element = inferred_type.shape.elements[0]
        assert isinstance(shape_element, Identifier_N)
        assert shape_element.name == "q"
    
    def test_single_df_selection_infers_scalar_shape(self):
        """Single DF selection f.in[x|0] should infer 0D array (scalar)."""
        gelb_code = real_lattice_program_1d(
            initializer_content="f.out[x|0] = f.in[x|0];"
        )
        ast = get_typed_ast(gelb_code)
        
        # Get the lattice IN selection
        initializer = ast.initializers.elements[0]
        assignment = initializer.stmts.elements[0]
        lattice_in_sel = assignment.rhs
        
        inferred_type = lattice_in_sel.inferred_type
        assert isinstance(inferred_type, ArrayDataType_N)
        assert inferred_type.scalar_dtype == "real"
        
        # Should be 0D array (scalar DF)
        assert len(inferred_type.shape.elements) == 0


class TestLatticeSelectionOperations:
    """Test lattice selections in various operation contexts."""
    
    def test_lattice_selection_in_arithmetic_operations(self):
        """Lattice selections used in arithmetic should maintain array types."""
        gelb_code = real_lattice_program_1d(
            initializer_content="f.out[x|:] = f.in[x|:] * 2.0;"
        )
        ast = get_typed_ast(gelb_code)
        
        # Get the multiplication expression
        initializer = ast.initializers.elements[0]
        assignment = initializer.stmts.elements[0]
        mul_expr = assignment.rhs
        
        assert isinstance(mul_expr, Mul_N)
        assert hasattr(mul_expr, 'inferred_type')
        assert isinstance(mul_expr.inferred_type, ArrayDataType_N)
        
        # Result should be vector (1D array) since lattice[x|:] * scalar
        assert len(mul_expr.inferred_type.shape.elements) == 1
        assert mul_expr.inferred_type.scalar_dtype == "real"
        
        # Left operand (lattice selection) should be vector
        lattice_sel = mul_expr.left
        assert isinstance(lattice_sel.inferred_type, ArrayDataType_N)
        assert len(lattice_sel.inferred_type.shape.elements) == 1
        
        # Right operand (scalar) should be 0D array
        scalar_lit = mul_expr.right
        assert isinstance(scalar_lit.inferred_type, ArrayDataType_N)
        assert len(scalar_lit.inferred_type.shape.elements) == 0
    
    def test_lattice_selection_addition_preserves_shapes(self):
        """Adding lattice selections should preserve array shapes."""
        gelb_code = real_lattice_program_1d(
            initializer_content="f.out[x|:] = f.in[x|:] + f.in[x|:];"
        )
        ast = get_typed_ast(gelb_code)
        
        # Get the addition expression
        initializer = ast.initializers.elements[0]
        assignment = initializer.stmts.elements[0]
        add_expr = assignment.rhs
        
        assert isinstance(add_expr, Add_N)
        assert hasattr(add_expr, 'inferred_type')
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        
        # Result should be vector (1D array)
        assert len(add_expr.inferred_type.shape.elements) == 1
        assert add_expr.inferred_type.scalar_dtype == "real"
        
        # Both operands should be vectors
        left_sel = add_expr.left
        right_sel = add_expr.right
        assert isinstance(left_sel.inferred_type, ArrayDataType_N)
        assert isinstance(right_sel.inferred_type, ArrayDataType_N)
        assert len(left_sel.inferred_type.shape.elements) == 1
        assert len(right_sel.inferred_type.shape.elements) == 1


class TestLatticeSelectionConsistency:
    """Test consistency of lattice selection type inference."""
    
    def test_identical_selections_have_identical_types(self):
        """Identical lattice selection patterns should have identical types."""
        gelb_code = real_lattice_program_1d(
            initializer_content="f.out[x|:] = f.in[x|:] + f.in[x|:];"
        )
        ast = get_typed_ast(gelb_code)
        
        # Get both lattice IN selections
        initializer = ast.initializers.elements[0]
        assignment = initializer.stmts.elements[0]
        add_expr = assignment.rhs
        
        left_sel = add_expr.left
        right_sel = add_expr.right
        
        # Both should be RectSelOfLatticeInDFs_N
        assert isinstance(left_sel, RectSelOfLatticeInDFs_N)
        assert isinstance(right_sel, RectSelOfLatticeInDFs_N)
        
        # Both should have identical types
        left_type = left_sel.inferred_type
        right_type = right_sel.inferred_type
        
        assert isinstance(left_type, ArrayDataType_N)
        assert isinstance(right_type, ArrayDataType_N)
        assert left_type.scalar_dtype == right_type.scalar_dtype
        assert len(left_type.shape.elements) == len(right_type.shape.elements)
    
    def test_in_vs_out_selection_type_compatibility(self):
        """IN and OUT selections with same patterns should have compatible types."""
        gelb_code = real_lattice_program_1d(
            initializer_content="f.out[x|:] = f.in[x|:];"
        )
        ast = get_typed_ast(gelb_code)
        
        # Get both selections
        initializer = ast.initializers.elements[0]
        assignment = initializer.stmts.elements[0]
        
        out_sel = assignment.lhs
        in_sel = assignment.rhs
        
        assert isinstance(out_sel, RectSelOfLatticeOutDFs_N)
        assert isinstance(in_sel, RectSelOfLatticeInDFs_N)
        
        # Both should have compatible array types
        out_type = out_sel.inferred_type
        in_type = in_sel.inferred_type
        
        assert isinstance(out_type, ArrayDataType_N)
        assert isinstance(in_type, ArrayDataType_N)
        assert out_type.scalar_dtype == in_type.scalar_dtype
        assert len(out_type.shape.elements) == len(in_type.shape.elements)


class TestLatticeSelectionIntegrationWithTypeSystem:
    """Test integration of lattice selections with the broader type system."""
    
    def test_lattice_selection_with_type_promotion(self):
        """Lattice selections should work correctly with type promotion."""
        gelb_code = real_lattice_program_1d(
            initializer_content="f.out[x|:] = f.in[x|:] + 1;"  # real + int -> real
        )
        ast = get_typed_ast(gelb_code)
        
        # Get the addition expression
        initializer = ast.initializers.elements[0]
        assignment = initializer.stmts.elements[0]
        add_expr = assignment.rhs
        
        assert isinstance(add_expr, Add_N)
        assert hasattr(add_expr, 'inferred_type')
        assert isinstance(add_expr.inferred_type, ArrayDataType_N)
        
        # Result should promote to real and maintain vector shape
        assert add_expr.inferred_type.scalar_dtype == "real"
        assert len(add_expr.inferred_type.shape.elements) == 1
        
        # Left operand (lattice) is real vector
        lattice_sel = add_expr.left
        assert lattice_sel.inferred_type.scalar_dtype == "real"
        assert len(lattice_sel.inferred_type.shape.elements) == 1
        
        # Right operand (integer literal) is int scalar (0D array)
        int_lit = add_expr.right
        assert int_lit.inferred_type.scalar_dtype == "int"
        assert len(int_lit.inferred_type.shape.elements) == 0
    
    def test_lattice_selection_in_dynamic_block(self):
        """Lattice selections should work correctly in dynamic blocks."""
        gelb_code = real_lattice_program_1d(
            dynamic_content="f.out[x|:] = f.in[x|:] * 0.5;"
        )
        ast = get_typed_ast(gelb_code)
        
        # Get the dynamic block assignment
        dynamic = ast.dynamics.elements[0]
        assignment = dynamic.stmts.elements[0]
        
        # Check that both selections are properly typed
        out_sel = assignment.lhs
        mul_expr = assignment.rhs
        in_sel = mul_expr.left
        
        assert isinstance(out_sel.inferred_type, ArrayDataType_N)
        assert isinstance(in_sel.inferred_type, ArrayDataType_N)
        assert out_sel.inferred_type.scalar_dtype == "real"
        assert in_sel.inferred_type.scalar_dtype == "real"
        assert len(out_sel.inferred_type.shape.elements) == 1
        assert len(in_sel.inferred_type.shape.elements) == 1


class TestLatticeSelectionDocumentation:
    """Document lattice selection type inference design principles."""
    
    def test_lattice_selection_design_principles(self):
        """Document key principles of lattice selection type inference."""
        gelb_code = real_lattice_program_1d(
            initializer_content="""
                f.out[x|0] = f.in[x|0];     // scalar DF -> 0D array
                f.out[x|:] = f.in[x|:];     // full DF -> 1D array
            """
        )
        ast = get_typed_ast(gelb_code)
        
        initializer = ast.initializers.elements[0]
        
        # First assignment: scalar DF selection
        scalar_assignment = initializer.stmts.elements[0]
        scalar_out = scalar_assignment.lhs
        scalar_in = scalar_assignment.rhs
        
        # Principle 1: Single DF selection is 0-dimensional array
        assert len(scalar_out.inferred_type.shape.elements) == 0
        assert len(scalar_in.inferred_type.shape.elements) == 0
        
        # Second assignment: full DF selection  
        vector_assignment = initializer.stmts.elements[1]
        vector_out = vector_assignment.lhs
        vector_in = vector_assignment.rhs
        
        # Principle 2: Full DF selection is 1-dimensional array
        assert len(vector_out.inferred_type.shape.elements) == 1
        assert len(vector_in.inferred_type.shape.elements) == 1
        
        # Principle 3: All use ArrayDataType_N universally
        for selection in [scalar_out, scalar_in, vector_out, vector_in]:
            assert isinstance(selection.inferred_type, ArrayDataType_N)
            assert selection.inferred_type.scalar_dtype == "real"