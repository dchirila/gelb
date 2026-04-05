#!/usr/bin/env python3

import pytest
from gelb.frontend.stage1_frontend import ASTBuilderVisitor, get_ast


def test_simple():
    # Arrange
    test_string = "node_class BULK(SetDFsToZero, SetDFsToOne, CurrentState);"
    # Act
    ast = get_ast("node_class_insta_stmt", test_string)
    # Assert
    assert str(ast) == (
        "(NodeClassInstaStmt"
        " (Identifier BULK)"
        " (Identifier SetDFsToZero)"
        " (Identifier SetDFsToOne)"
        " (Identifier CurrentState)"
        ")"
    )


def test_no_dynamic():
    """Node class with no dynamic (static node)."""
    test_string = "node_class WALL(InitWall, Temperature);"
    ast = get_ast("node_class_insta_stmt", test_string)
    assert str(ast) == (
        "(NodeClassInstaStmt"
        " (Identifier WALL)"
        " (Identifier InitWall)"
        " (Identifier Temperature)"
        ")"
    )
    assert ast.dynamic is None
    assert ast.masked is False


def test_masked_with_dynamic():
    """Masked node class with init + dynamic, no gauge."""
    test_string = "node_class WALL(Init, BounceBack) masked;"
    ast = get_ast("node_class_insta_stmt", test_string)
    assert ast.masked is True
    assert ast.initializer is not None
    assert ast.dynamic is not None
    assert ast.gauge is None
    assert str(ast) == (
        "(NodeClassInstaStmt"
        " (Identifier WALL)"
        " (Identifier Init)"
        " (Identifier BounceBack)"
        " masked)"
    )


def test_masked_init_only():
    """Masked node class with init only."""
    test_string = "node_class SW(InitWall) masked;"
    ast = get_ast("node_class_insta_stmt", test_string)
    assert ast.masked is True
    assert ast.initializer is not None
    assert ast.dynamic is None
    assert ast.gauge is None
    assert str(ast) == (
        "(NodeClassInstaStmt"
        " (Identifier SW)"
        " (Identifier InitWall)"
        " masked)"
    )


def test_masked_empty():
    """Masked node class with no args (pure solid marker)."""
    test_string = "node_class SOLID() masked;"
    ast = get_ast("node_class_insta_stmt", test_string)
    assert ast.masked is True
    assert ast.initializer is None
    assert ast.dynamic is None
    assert ast.gauge is None
    assert str(ast) == "(NodeClassInstaStmt (Identifier SOLID) masked)"


# ----------------------------------------------------------------------
# Grammar contract tests for the masked variant.
#
# These tests assert that the grammar itself rejects invalid combinations
# of `masked` with too many arguments.  The combinations are forbidden
# at the grammar level (not by a separate validator), because masked
# cells are skipped at the runtime gauge sweep and a 3-arg variant would
# imply a gauge that can never run.
# ----------------------------------------------------------------------

def test_masked_with_three_args_is_rejected():
    """`node_class FOO(init, dyn, gauge) masked;` must be a parse error.

    The grammar has no 3-identifier alternative followed by `masked`,
    so a 3-arg masked variant is structurally impossible.  Masked
    cells are excluded from the gauge sweep at runtime, so adding a
    gauge would be meaningless.
    """
    from gelb.utils.exceptions import GeLBExSyntaxError
    test_string = "node_class WALL(Init, Dyn, Gauge) masked;"
    with pytest.raises(GeLBExSyntaxError):
        get_ast("node_class_insta_stmt", test_string)


def test_masked_with_three_args_error_message_is_helpful():
    """The error message must explain the masked + gauge constraint.

    Without this, users see ANTLR's cryptic
    `extraneous input 'masked' expecting ';'` and have no idea what's
    wrong.
    """
    from gelb.utils.exceptions import GeLBExSyntaxError
    test_string = "node_class WALL(Init, Dyn, Gauge) masked;"
    with pytest.raises(GeLBExSyntaxError) as exc_info:
        get_ast("node_class_insta_stmt", test_string)
    hint = exc_info.value.hint
    assert "masked" in hint
    assert "gauge" in hint.lower()


def test_unmasked_with_one_arg_is_rejected():
    """`node_class FOO(init);` (no dynamic, no gauge) must be a parse error.

    A non-masked node class needs at least an initializer + gauge.
    """
    from gelb.utils.exceptions import GeLBExSyntaxError
    test_string = "node_class FOO(Init);"
    with pytest.raises(GeLBExSyntaxError):
        get_ast("node_class_insta_stmt", test_string)


def test_unmasked_with_zero_args_is_rejected():
    """`node_class FOO();` must be a parse error.

    Only the masked variant allows a zero-argument form.
    """
    from gelb.utils.exceptions import GeLBExSyntaxError
    test_string = "node_class FOO();"
    with pytest.raises(GeLBExSyntaxError):
        get_ast("node_class_insta_stmt", test_string)
