#!/usr/bin/env python3
"""Tests for generic AST child traversal."""

from gelb.gelb_ast.ASTNodes import IntLiteral_N, Program_N


_PASS_METADATA_FIELDS = {
    'inferred_type',
    'symbol_tag',
    'function_block',
    'is_full_df_range',
    'collinearity_rewrites',
    'slice_df_expansions',
    'cse_temps_emitted',
}


def test_pass_metadata_fields_are_not_ast_children():
    node = IntLiteral_N(code_range=None, value=42)

    for field_name in _PASS_METADATA_FIELDS:
        setattr(node, field_name, IntLiteral_N(code_range=None, value=7))

    child_names = set(node.get_children_names())
    children = set(node.get_children())

    assert 'value' in child_names
    assert child_names.isdisjoint(_PASS_METADATA_FIELDS)
    assert all(
        getattr(node, field_name) not in children
        for field_name in _PASS_METADATA_FIELDS
    )


def test_program_pass_metadata_fields_are_not_ast_children():
    ast = Program_N(code_range=None)

    for field_name in _PASS_METADATA_FIELDS:
        setattr(ast, field_name, IntLiteral_N(code_range=None, value=7))

    child_names = set(ast.get_children_names())

    assert 'simulation_description' in child_names
    assert child_names.isdisjoint(_PASS_METADATA_FIELDS)
