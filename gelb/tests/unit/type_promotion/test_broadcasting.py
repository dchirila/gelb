#!/usr/bin/env python3
"""
Unit tests for scalar-to-array broadcasting functionality.

Tests the BroadcastNode_N AST node and its integration with the type system.
"""

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import (
    get_typed_ast,
    minimal_gelb_program_1d,
    minimal_gelb_program_2d,
    minimal_gelb_program_3d
)
from gelb.frontend.stage1_frontend import (
    get_ast,
    build_symbols_tables,
    add_implicit_symbols,
    resolve_all_constants,
    resolve_ranges,
    infer_types,
    promote_types
)


class TestScalarToArrayBroadcasting:
    """Test scalar-to-array broadcasting in assignments."""
    
    def test_broadcast_int_to_real_array_1d(self):
        """Test broadcasting integer scalar to 1D real array."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[real, 5] vec;
                vec = 42;
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]  # vec = 42;
        
        # Check that RHS is a BroadcastNode
        assert isinstance(assignment.rhs, BroadcastNode_N)
        
        # Check the broadcast node structure
        broadcast = assignment.rhs
        assert isinstance(broadcast.scalar_expr, TypePromotionNode_N)  # int->real promotion
        assert isinstance(broadcast.scalar_expr.expr, IntLiteral_N)
        assert broadcast.scalar_expr.expr.value == 42
        
        # Check target array type
        assert isinstance(broadcast.target_array_type, ArrayDataType_N)
        assert broadcast.target_array_type.element_dtype == "real"
        assert isinstance(broadcast.target_array_type.shape, IntLiteral_N)
        assert broadcast.target_array_type.shape.value == 5
    
    def test_broadcast_real_to_real_array_2d(self):
        """Test broadcasting real scalar to 2D real array."""
        test_program = minimal_gelb_program_2d(
            initializer_content="""
                array[real, {3, 4}] matrix;
                matrix = 3.14;
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]  # matrix = 3.14;
        
        # Check that RHS is a BroadcastNode
        assert isinstance(assignment.rhs, BroadcastNode_N)
        
        # Check the broadcast node structure (no promotion needed for real->real)
        broadcast = assignment.rhs
        assert isinstance(broadcast.scalar_expr, RealLiteral_N)
        assert broadcast.scalar_expr.value == 3.14
        
        # Check target array type
        assert isinstance(broadcast.target_array_type, ArrayDataType_N)
        assert broadcast.target_array_type.element_dtype == "real"
        assert isinstance(broadcast.target_array_type.shape, Array1DLiteral_N)
        shape_elements = broadcast.target_array_type.shape.value.elements
        assert len(shape_elements) == 2
        assert shape_elements[0].value == 3
        assert shape_elements[1].value == 4
    
    def test_broadcast_bool_to_bool_array_3d(self):
        """Test broadcasting boolean scalar to 3D bool array."""
        test_program = minimal_gelb_program_3d(
            initializer_content="""
                array[bool, {2, 2, 2}] flags;
                flags = true;
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]  # flags = true;
        
        # Check that RHS is a BroadcastNode
        assert isinstance(assignment.rhs, BroadcastNode_N)
        
        # Check the broadcast node structure
        broadcast = assignment.rhs
        assert isinstance(broadcast.scalar_expr, BoolLiteral_N)
        assert broadcast.scalar_expr.value == "true"
        
        # Check target array type
        assert isinstance(broadcast.target_array_type, ArrayDataType_N)
        assert broadcast.target_array_type.element_dtype == "bool"
    
    def test_broadcast_with_type_promotion_bool_to_int(self):
        """Test broadcasting with type promotion from bool to int array."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 10] counts;
                counts = true;  // bool promoted to int, then broadcast
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        
        # Check that RHS is a BroadcastNode
        assert isinstance(assignment.rhs, BroadcastNode_N)
        
        # Check the broadcast node has a promotion inside
        broadcast = assignment.rhs
        assert isinstance(broadcast.scalar_expr, TypePromotionNode_N)
        assert isinstance(broadcast.scalar_expr.expr, BoolLiteral_N)
        assert broadcast.scalar_expr.target_type.element_dtype == "int"
    
    def test_no_broadcast_for_array_to_array(self):
        """Test that array-to-array assignment doesn't create broadcast nodes."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[int, 3] src;
                array[int, 3] dst;
                src[0] = 1;
                src[1] = 2;
                src[2] = 3;
                dst = src;  // array-to-array, no broadcast
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the last assignment statement (dst = src)
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[-1]
        
        # Check that RHS is NOT a BroadcastNode
        assert not isinstance(assignment.rhs, BroadcastNode_N)
        assert isinstance(assignment.rhs, Identifier_N)
        assert assignment.rhs.name == "src"
    
    def test_broadcast_to_array_element_selection(self):
        """Test that single element assignment doesn't create broadcast nodes."""
        test_program = minimal_gelb_program_2d(
            initializer_content="""
                array[real, {2, 3}] matrix;
                matrix[0, 0] = 1.5;  // single element, no broadcast
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        
        # Check that RHS is NOT a BroadcastNode (single element assignment)
        assert not isinstance(assignment.rhs, BroadcastNode_N)
        assert isinstance(assignment.rhs, RealLiteral_N)
    
    def test_broadcast_with_constant_expression(self):
        """Test broadcasting a constant expression to an array."""
        test_program = minimal_gelb_program_1d(
            global_constants_content="""
                const int SIZE = 5;
                const real PI = 3.14159;
            """,
            initializer_content="""
                array[real, SIZE] values;
                values = 2 * PI;  // constant expression broadcast
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        
        # Check that RHS is a BroadcastNode
        assert isinstance(assignment.rhs, BroadcastNode_N)
        
        # The scalar expression should be the multiplication
        broadcast = assignment.rhs
        assert isinstance(broadcast.scalar_expr, Mul_N)
    
    def test_broadcast_node_string_representation(self):
        """Test the string representation of BroadcastNode_N."""
        # Create a broadcast node manually
        scalar = IntLiteral_N(None, 42)
        target_type = ArrayDataType_N(None, "int", IntLiteral_N(None, 5))
        broadcast = BroadcastNode_N(None, scalar, target_type)
        
        # Check string representation
        assert str(broadcast) == "(Broadcast (IntLiteral 42) -> (ArrayDataType int (IntLiteral 5)))"
    
    def test_broadcast_node_children(self):
        """Test that BroadcastNode_N properly reports its children."""
        # Create a broadcast node manually
        scalar = IntLiteral_N(None, 42)
        target_type = ArrayDataType_N(None, "int", IntLiteral_N(None, 5))
        broadcast = BroadcastNode_N(None, scalar, target_type)
        
        # Check children
        children = broadcast.get_children()
        assert scalar in children
        assert target_type in children
        assert len(children) == 2


class TestBroadcastingEdgeCases:
    """Test edge cases and error conditions for broadcasting."""
    
    def test_nested_arrays_no_broadcast(self):
        """Test that nested array types don't support broadcasting."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[array[int, 3], 2] nested;
                // This should fail during parsing, not reach broadcasting
            """
        )
        
        # This should fail during parsing since nested arrays aren't supported
        with pytest.raises(Exception):
            ast = get_ast("gelb_program", test_program)
    
    def test_broadcast_preserves_inferred_type(self):
        """Test that broadcast nodes have correct inferred type."""
        test_program = minimal_gelb_program_1d(
            initializer_content="""
                array[real, 8] data;
                data = 0;
            """
        )
        
        # Process through type promotion stage
        ast = get_ast("gelb_program", test_program)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        
        # Find the assignment statement
        init_block = ast.initializers.elements[0]
        assignment = init_block.stmts.elements[1]
        
        # Check broadcast node's inferred type
        broadcast = assignment.rhs
        assert hasattr(broadcast, 'inferred_type')
        assert isinstance(broadcast.inferred_type, ArrayDataType_N)
        assert broadcast.inferred_type.element_dtype == "real"
        assert isinstance(broadcast.inferred_type.shape, IntLiteral_N)
        assert broadcast.inferred_type.shape.value == 8


class TestArrayArithmeticShapePreservation:
    """Regression guard: TypePromotionVisitor must preserve the array
    shape computed by TypeInferenceVisitor for arithmetic operations.

    Before the fix, ``_handle_arithmetic_binary_op`` unconditionally
    overwrote the inferred shape with an empty (scalar) List_N, which
    caused valid programs like

        const array[real, 9] EX = {...};
        const array[real, 9] EX_EX = EX * EX;

    to be rejected by the type validator with a misleading "declared
    as 'real' but initialized with 'real'" error -- because the shape
    had been clobbered from ``array[real, 9]`` to ``scalar real``,
    even though the element type was correct.
    """

    @staticmethod
    def _run_frontend(src):
        ast = get_ast("gelb_program", src)
        ast = build_symbols_tables(ast)
        ast = add_implicit_symbols(ast)
        ast = resolve_all_constants(ast)
        ast = resolve_ranges(ast)
        ast = infer_types(ast)
        ast = promote_types(ast)
        return ast

    def test_array_times_array_preserves_shape_in_const_def(self):
        """``const array[real, 9] EX_EX = EX * EX;`` must keep shape."""
        src = """
        simulation_description("array * array shape preservation");
        global_constants {
            const array[real, 9] EX = {0.0, 1.0, 0.0, -1.0, 0.0, 1.0, -1.0, -1.0, 1.0};
            const array[real, 9] EX_EX = EX * EX;
        }
        lattices { lattice f(2, 9, real, {8, 8}, {true, true}); }
        initializer Init { f.out[x, y | :] = EX; }
        dynamic Dyn { f.out[x, y | :] = f.in[x, y | :]; }
        gauge G -> (real v) { v = f.in[x, y | 0]; }
        node_classes { node_class BULK(Init, Dyn, G); }
        geometry { nodes[:, :] = BULK; }
        """
        ast = self._run_frontend(src)

        # Find the EX_EX constant definition and check the inferred
        # type of its RHS (the Mul_N).
        stmts = ast.global_constants.stmts
        ex_ex = None
        for stmt in stmts:
            if getattr(stmt.name, 'name', None) == 'EX_EX':
                ex_ex = stmt
                break
        assert ex_ex is not None, "EX_EX constant not found"

        rhs = ex_ex.value
        assert isinstance(rhs, Mul_N), \
            f"RHS should be a Mul_N, got {type(rhs).__name__}"
        assert hasattr(rhs, 'inferred_type'), \
            "Mul_N should have inferred_type after promotion"

        rhs_type = rhs.inferred_type
        assert isinstance(rhs_type, ArrayDataType_N), \
            f"RHS type should be ArrayDataType_N, got {type(rhs_type).__name__}"
        assert rhs_type.element_dtype == 'real', \
            f"RHS element type should be 'real', got {rhs_type.element_dtype!r}"

        # The shape must NOT have been clobbered to scalar.  It should
        # still be IntLiteral_N(9) (1D array of length 9).
        shape = rhs_type.shape
        assert isinstance(shape, IntLiteral_N), (
            f"Shape should be IntLiteral_N(9) after promotion, got "
            f"{type(shape).__name__} — the promotion visitor is "
            f"clobbering the shape to scalar again")
        assert shape.value == 9, \
            f"Shape value should be 9, got {shape.value}"

    def test_array_plus_array_preserves_shape(self):
        """``array + array`` (Add_N) must also preserve shape."""
        src = """
        simulation_description("array + array shape preservation");
        global_constants {
            const array[real, 9] A = {1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0};
            const array[real, 9] B = {2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0};
            const array[real, 9] SUM = A + B;
        }
        lattices { lattice f(2, 9, real, {8, 8}, {true, true}); }
        initializer Init { f.out[x, y | :] = SUM; }
        dynamic Dyn { f.out[x, y | :] = f.in[x, y | :]; }
        gauge G -> (real v) { v = f.in[x, y | 0]; }
        node_classes { node_class BULK(Init, Dyn, G); }
        geometry { nodes[:, :] = BULK; }
        """
        ast = self._run_frontend(src)
        stmts = ast.global_constants.stmts
        sum_stmt = next(s for s in stmts
                        if getattr(s.name, 'name', None) == 'SUM')
        rhs = sum_stmt.value
        assert isinstance(rhs, Add_N)
        assert isinstance(rhs.inferred_type, ArrayDataType_N)
        assert rhs.inferred_type.element_dtype == 'real'
        assert isinstance(rhs.inferred_type.shape, IntLiteral_N)
        assert rhs.inferred_type.shape.value == 9

    def test_array_times_scalar_still_works(self):
        """Regression guard: ``array * scalar`` was already working,
        make sure the fix didn't break it."""
        src = """
        simulation_description("array * scalar");
        global_constants {
            const array[real, 9] EX = {0.0, 1.0, 0.0, -1.0, 0.0, 1.0, -1.0, -1.0, 1.0};
            const array[real, 9] TWO_EX = EX * 2.0;
        }
        lattices { lattice f(2, 9, real, {8, 8}, {true, true}); }
        initializer Init { f.out[x, y | :] = TWO_EX; }
        dynamic Dyn { f.out[x, y | :] = f.in[x, y | :]; }
        gauge G -> (real v) { v = f.in[x, y | 0]; }
        node_classes { node_class BULK(Init, Dyn, G); }
        geometry { nodes[:, :] = BULK; }
        """
        ast = self._run_frontend(src)
        stmts = ast.global_constants.stmts
        two_ex = next(s for s in stmts
                      if getattr(s.name, 'name', None) == 'TWO_EX')
        rhs = two_ex.value
        assert isinstance(rhs, Mul_N)
        assert isinstance(rhs.inferred_type, ArrayDataType_N)
        assert rhs.inferred_type.element_dtype == 'real'
        assert isinstance(rhs.inferred_type.shape, IntLiteral_N)
        assert rhs.inferred_type.shape.value == 9

def test_a_scalar_initializer_of_an_array_declaration_is_broadcast():
    """``array[real, 3] t = <scalar>`` gets the broadcast an assignment
    gets, so every backend sees one node (user manual, Numerical
    semantics: Types and promotion)."""
    from gelb.frontend.stage1_frontend import promote_types
    from gelb.gelb_ast.ASTNodes import BroadcastNode_N, IntrinsicFunctionCall_N
    from gelb.tests.test_utils import get_typed_ast, minimal_gelb_program_1d
    ast = promote_types(get_typed_ast(minimal_gelb_program_1d(
        initializer_content="array[real, 3] t = min(1.5, 2.0 * x);\nf.out[x | 0] = 0;")))
    decl = ast.initializers[0].stmts.elements[0]
    assert isinstance(decl.initial_value, BroadcastNode_N)
    assert decl.initial_value.target_array_type.element_dtype == "real"
    assert isinstance(decl.initial_value.scalar_expr, IntrinsicFunctionCall_N)
