#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import validate_ast_root_is_program
from gelb.gelb_ast.ASTNodes import Program_N, IntLiteral_N
from gelb.utils.exceptions import GeLBException
from gelb.utils.CodeRange import CodeRange


def test_validate_ast_root_is_program_with_valid_root():
    """Test that validation passes for Program_N root."""
    # Create a valid Program_N node
    ast_root = Program_N(CodeRange(0, 0, 0, 0))
    
    # Should not raise any exception
    validate_ast_root_is_program(ast_root)


def test_validate_ast_root_is_program_with_invalid_root():
    """Test that validation fails for non-Program_N root."""
    # Create a non-Program_N node
    ast_root = IntLiteral_N(CodeRange(0, 0, 0, 0), 42)
    
    # Should raise GeLBException
    with pytest.raises(GeLBException) as exc_info:
        validate_ast_root_is_program(ast_root)
    
    # Check error message
    assert "Expected Program_N root node" in str(exc_info.value.error)
    assert "IntLiteral_N" in str(exc_info.value.error)