#!/usr/bin/env python3

import pytest
from gelb.tests.unit.ast_building.ast_test_utils import assert_ast_equals, get_expression_ast_test_data


class TestExpressionAST:
    """Consolidated tests for expression AST building across all expression types."""

    @pytest.mark.parametrize("category,test_name,test_string,expected", get_expression_ast_test_data())
    def test_expression_ast(self, category, test_name, test_string, expected):
        """Test AST building for all expression types."""
        assert_ast_equals(test_string, expected, "expr")


class TestExpressionASTFunctionCalls:
    """Regression tests for ``visitExpr`` function-call dispatch.

    Earlier versions of ``visitExpr`` had a manual if/elif chain that
    omitted ``IntrinsicFunctionCallExprContext`` and
    ``UserFunctionCallExprContext``, so parsing a bare expression like
    ``int(3.7)`` or ``MyFunc(a)`` via ``get_ast("expr", ...)`` raised
    ``AssertionError: Unknown expression type``.  Now ``visitExpr``
    delegates to ``ctx.accept(self)`` (ANTLR's auto-dispatch), so all
    labeled alternatives work.  These tests lock that contract in.
    """

    def test_intrinsic_call_via_expr_entry_point(self):
        from gelb.frontend.stage1_frontend import get_ast
        ast = get_ast("expr", "int(3.7)")
        from gelb.gelb_ast.ASTNodes import IntrinsicFunctionCall_N
        assert isinstance(ast, IntrinsicFunctionCall_N)
        assert ast.function_name == "int"

    def test_math_intrinsic_via_expr_entry_point(self):
        from gelb.frontend.stage1_frontend import get_ast
        ast = get_ast("expr", "sin(3.14)")
        from gelb.gelb_ast.ASTNodes import IntrinsicFunctionCall_N
        assert isinstance(ast, IntrinsicFunctionCall_N)
        assert ast.function_name == "sin"

    def test_user_function_call_via_expr_entry_point(self):
        from gelb.frontend.stage1_frontend import get_ast
        ast = get_ast("expr", "MyFunc(a, b)")
        from gelb.gelb_ast.ASTNodes import UserFunctionCall_N
        assert isinstance(ast, UserFunctionCall_N)
        assert ast.function_name.name == "MyFunc"

    def test_cast_intrinsic_via_expr_entry_point(self):
        """All eight cast-intrinsic names parse via the expr entry point;
        real16(x) is rejected as not in this version."""
        import pytest
        from gelb.frontend.stage1_frontend import get_ast
        from gelb.gelb_ast.ASTNodes import IntrinsicFunctionCall_N
        from gelb.utils.exceptions import GeLBExTypeError
        for name in ('int', 'int8', 'int16', 'int32', 'int64',
                     'real', 'real32', 'real64'):
            ast = get_ast("expr", f"{name}(x)")
            assert isinstance(ast, IntrinsicFunctionCall_N), \
                f"{name}(x) did not parse as IntrinsicFunctionCall_N"
            assert ast.function_name == name
        with pytest.raises(GeLBExTypeError, match="not in this version"):
            get_ast("expr", "real16(x)")