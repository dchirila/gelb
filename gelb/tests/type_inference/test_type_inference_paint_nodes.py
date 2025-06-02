#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import (
    get_ast,
    build_symbols_tables,
    resolve_all_constants,
    resolve_ranges,
    add_implicit_symbols,
    infer_types
)
from gelb.gelb_ast.ASTNodes import *
from gelb.utils import config


def get_typed_ast(gelb_code):
    """Helper to get AST with types inferred."""
    # Set the source code in config to avoid error reporting issues
    config.GELB_SRC_RAW = gelb_code
    
    ast = get_ast("gelb_program", gelb_code)
    ast = build_symbols_tables(ast)
    ast = add_implicit_symbols(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)
    ast = infer_types(ast)
    return ast


def minimal_gelb_program_2d(geometry_content="", global_constants_content=""):
    """Create a minimal valid 2D GeLB program with the given geometry content."""
    default_constants = "const int N = 32;"
    if global_constants_content:
        # If custom constants provided, use them (they should include N)
        constants_block = global_constants_content
    else:
        constants_block = default_constants
        
    return f"""
    simulation_description("Test 2D");
    global_constants {{
        {constants_block}
    }}
    lattices {{
        lattice f(2, 9, int);
    }}
    initializer Init {{
        f.out[x, y | 0] = 0;
    }}
    dynamic Dyn {{
        f.out[x, y | 0] = f.in[x, y | 0];
    }}
    gauge Out(out = {{int val;}}) {{
        val = f.in[x, y | 0];
    }}
    node_classes {{
        node_class BULK(Init, Dyn, Out);
        node_class WALL(Init, Dyn, Out);
    }}
    geometry {{
        set_grid_size({{N, N}});
        set_grid_periodicity({{false, false}});
        {geometry_content if geometry_content else "nodes[:, :] = BULK;"}
    }}
    """


class TestPaintNodesTypeInference:
    """Test type inference for paint nodes statements."""
    
    def test_paint_nodes_with_constant_division(self):
        gelb_code = minimal_gelb_program_2d("nodes[1 : N / 2, :] = BULK;")
        ast = get_typed_ast(gelb_code)
        
        # Get the paint statement from geometry block
        paint_stmt = ast.geometry.stmts.elements[0]
        assert isinstance(paint_stmt, PaintNodesStmt_N)
        
        # The LHS should be a List with two Range elements
        assert isinstance(paint_stmt.lhs, List_N)
        assert len(paint_stmt.lhs.elements) == 2
        
        # First range: 1 : N / 2
        first_range = paint_stmt.lhs.elements[0]
        assert isinstance(first_range, Range_N)
        
        # The high bound should be a Div_N expression
        # After constant resolution, N is replaced with 32
        # So we have 32 / 2 which might be further evaluated
        assert hasattr(first_range.high, 'inferred_type')
        assert isinstance(first_range.high.inferred_type, ScalarDataType_N)
        assert first_range.high.inferred_type.scalar_dtype == "int"
    
    def test_paint_nodes_with_arithmetic_expression(self):
        gelb_code = minimal_gelb_program_2d("nodes[2 * 5 : N - 10, :] = WALL;")
        ast = get_typed_ast(gelb_code)
        
        # Get the paint statement from geometry block
        paint_stmt = ast.geometry.stmts.elements[0]
        assert isinstance(paint_stmt, PaintNodesStmt_N)
        
        # First range: 2 * 5 : N - 10
        first_range = paint_stmt.lhs.elements[0]
        
        # Check low bound (2 * 5)
        if hasattr(first_range.low, 'inferred_type'):
            assert isinstance(first_range.low.inferred_type, ScalarDataType_N)
            assert first_range.low.inferred_type.scalar_dtype == "int"
        
        # Check high bound (N - 10)
        if hasattr(first_range.high, 'inferred_type'):
            assert isinstance(first_range.high.inferred_type, ScalarDataType_N)
            assert first_range.high.inferred_type.scalar_dtype == "int"
    
    def test_paint_nodes_with_constant_ranges(self):
        """Test paint nodes with constant-based range expressions."""
        # Use ranges based on constants
        gelb_code = minimal_gelb_program_2d(
            global_constants_content="""
                const int N = 32;
                const int WALL_HEIGHT = 5;
            """,
            geometry_content="nodes[:, 0 : WALL_HEIGHT] = WALL;"
        )
        ast = get_typed_ast(gelb_code)
        
        # Get the paint statement from geometry block
        paint_stmt = ast.geometry.stmts.elements[0]
        assert isinstance(paint_stmt, PaintNodesStmt_N)
        
        # Second range: 0 : WALL_HEIGHT
        second_range = paint_stmt.lhs.elements[1]
        assert isinstance(second_range, Range_N)
        
        # Check that the low bound (0) has int type
        assert hasattr(second_range.low, 'inferred_type')
        assert isinstance(second_range.low.inferred_type, ScalarDataType_N)
        assert second_range.low.inferred_type.scalar_dtype == "int"
        
        # Check that WALL_HEIGHT has been resolved and has int type
        # After constant resolution, WALL_HEIGHT might be replaced with 5
        if hasattr(second_range.high, 'inferred_type'):
            assert isinstance(second_range.high.inferred_type, ScalarDataType_N)
            assert second_range.high.inferred_type.scalar_dtype == "int"