#!/usr/bin/env python3

import copy
import math

from gelb.frontend.ASTBaseVisitor import ASTBaseVisitor
from gelb.frontend.visitor_mixins import ProgramTraversalMixin
from gelb.frontend.intrinsic_functions import (
    CAST_INTRINSIC_NAMES, INT_CAST_NAMES, REAL_CAST_NAMES,
)
from gelb.gelb_ast.ASTNodes import *
from gelb.frontend.type_rules import SCALAR_INTRINSICS
from gelb.midware.ast_eval import (
    NARROW_INT_WIDTHS, NARROW_REAL_WIDTHS, ConstantEvaluationError, add,
    convert, convert_plain, divide, ieee_special_values, intrinsic, mul,
    narrow_scalar, negate, plain, power, sub, typed_literal_value)

_REAL_WIDTHS = frozenset(('real', 'real64')) | NARROW_REAL_WIDTHS
_INT_WIDTHS = frozenset(('int', 'int64')) | NARROW_INT_WIDTHS
from gelb.utils.exceptions import GeLBException, GeLBExTypeError
from gelb.utils.CodeRange import CodeRange


class ConstantFoldingVisitor(ASTBaseVisitor, ProgramTraversalMixin):
    """
    Performs constant folding optimizations on the AST.
    
    This visitor evaluates constant expressions at compile time and replaces
    them with their computed literal values. This optimization:
    
    1. Improves runtime performance by eliminating redundant calculations
    2. Enables better optimization in subsequent passes
    3. Supports division by zero detection by simplifying expressions like (1-1) to 0
    4. Works with type promotion expansion to maximize constant propagation
    
    Must run after:
    - Type inference (needs inferred_type on nodes)
    - Constant resolution (needs constants to be resolved)
    
    Should run before:
    - Type promotion expansion (to maximize constant promotion opportunities)
    - Division by zero detection (to detect zeros in expressions)
    """
    
    def __init__(self):
        super().__init__()
    
    # Program traversal
    
    def visitProgram_N(self, node: Program_N, ast_root_node: Program_N):
        """Visit all blocks in the program to apply constant folding.

        The evaluator runs in its IEEE mode: a constant operation that
        overflows or is invalid (``exp(1000.0)``, ``sqrt(-1.0)``,
        ``1.0e300 * 1.0e300``, ``real32(1.0e300)``) folds to the value
        the run time would give, an infinity or a NaN, written into
        the literal; the backends emit such a literal as an explicit
        special value (user manual, Numerical semantics: Constant
        folding; tests in ``test_nonfinite_folding.py``).
        """
        with ieee_special_values():
            self.traverse_program_blocks(node, ast_root_node)
        return node
    
    def _store_global_constants(self, node):
        """Hook for storing global constants block."""
        self.global_constants_block = node.global_constants
    
    def _before_block_visit(self, block_node, block_type):
        """Set current block context before visiting."""
        self.current_block = block_node
        self._current_block_type = block_type
    
    # Arithmetic operations
    
    def visitAdd_N(self, node: Add_N, ast_root_node: Program_N):
        """Fold addition operations."""
        return self._handle_arithmetic_binary_op(
            node, ast_root_node, self._evaluate_add, add)

    def visitSub_N(self, node: Sub_N, ast_root_node: Program_N):
        """Fold subtraction operations."""
        return self._handle_arithmetic_binary_op(
            node, ast_root_node, self._evaluate_sub, sub)

    def visitMul_N(self, node: Mul_N, ast_root_node: Program_N):
        """Fold multiplication operations."""
        return self._handle_arithmetic_binary_op(
            node, ast_root_node, self._evaluate_mul, mul)

    def visitDiv_N(self, node: Div_N, ast_root_node: Program_N):
        """Fold division operations."""
        # No element-wise array-fold for div: integer-vs-real semantics
        # are subtle (see _evaluate_div) and array-by-array division
        # isn't an idiom in any current example.
        return self._handle_arithmetic_binary_op(
            node, ast_root_node, self._evaluate_div, raw_op=None)

    def visitPow_N(self, node: Pow_N, ast_root_node: Program_N):
        """Fold exponentiation operations."""
        return self._handle_arithmetic_binary_op(
            node, ast_root_node, self._evaluate_pow, raw_op=None)
    
    def _handle_arithmetic_binary_op(self, node, ast_root_node, evaluator,
                                     raw_op=None):
        """
        Generic handler for arithmetic binary operations.

        Args:
            node: The binary operation node
            ast_root_node: Root of the AST
            evaluator: Literal-node-typed evaluator (uses isinstance
                checks for Int/RealLiteral_N) -- used for the scalar
                fold path.
            raw_op: Optional callable(a, b) over raw Python numbers,
                used by the array-fold path.  Pass None to disable
                array folding for this op (e.g. ``Div_N`` with mixed
                int/real semantics, ``Pow_N``).
        """
        # Visit children first (bottom-up processing)
        node.left = self.visit(node.left, ast_root_node)
        node.right = self.visit(node.right, ast_root_node)

        # Check if both operands are constant literals
        if self._is_constant_literal(node.left) and self._is_constant_literal(node.right):
            try:
                result_value = evaluator(node.left, node.right)
            except ConstantEvaluationError as exc:
                raise self._diagnostic(node, exc)
            except ZeroDivisionError:
                # a visible zero divisor: DivisionByZeroValidator reports it
                result_value = None
            except (OverflowError, ValueError):
                # an operation the evaluator cannot perform here (the
                # IEEE mode makes a real overflow or domain error a value)
                result_value = None
            if self._is_foldable_result(result_value):
                result_literal = self._create_literal_from_value(result_value, node)
                if result_literal is not None:
                    return result_literal

        # Array-arithmetic fold: element-wise op for Array1DLiteral_N
        # operands (with scalar broadcast).  Enables const initialisers
        # like `const array[real, 9] EX_EX = EX * EX;` to fold ahead of
        # any backend that consumes the array as a literal.
        if raw_op is not None:
            array_result = self._try_fold_array_arithmetic(node, raw_op)
            if array_result is not None:
                return array_result

        return node

    def _try_fold_array_arithmetic(self, node, raw_op):
        """Fold element-wise arithmetic on Array1DLiteral_N operands.

        Handles three cases:
          * array op array (lengths must match)
          * scalar op array
          * array op scalar
        Returns the folded Array1DLiteral_N, or None if either operand
        is not a constant array/scalar (let the backend handle non-
        const cases at runtime).
        """
        left_arr = self._is_constant_array(node.left)
        right_arr = self._is_constant_array(node.right)
        left_scalar = self._is_foldable_scalar(node.left)
        right_scalar = self._is_foldable_scalar(node.right)

        # Need at least one constant array to fold; the other side
        # must also be foldable (constant array or scalar).
        if not (left_arr or right_arr):
            return None
        if left_arr and not (right_arr or right_scalar):
            return None
        if right_arr and not (left_arr or left_scalar):
            return None

        # Reject 2-D: matmul has its own path; element-wise 2-D
        # arithmetic isn't an idiom in any current example.
        left_unwrapped = self._unwrap_promotion(node.left)
        right_unwrapped = self._unwrap_promotion(node.right)
        if isinstance(left_unwrapped, Array2DLiteral_N) or \
                isinstance(right_unwrapped, Array2DLiteral_N):
            return None

        # Each element computes in its operand's element width, as the
        # scalar fold does (the evaluator checks integer overflow and
        # rounds a real result once).
        left_width = self._element_dtype(node.left)
        right_width = self._element_dtype(node.right)
        try:
            if left_arr and right_arr:
                lv = self._typed_vector(node.left, left_width)
                rv = self._typed_vector(node.right, right_width)
                if len(lv) != len(rv):
                    return None  # type-system bug surface; don't crash here
                result = [raw_op(l, r) for l, r in zip(lv, rv)]
            elif left_arr:
                lv = self._typed_vector(node.left, left_width)
                rs = self._scalar_value(node.right)
                result = [raw_op(l, rs) for l in lv]
            else:  # right_arr
                ls = self._scalar_value(node.left)
                rv = self._typed_vector(node.right, right_width)
                result = [raw_op(ls, r) for r in rv]
        except ConstantEvaluationError as exc:
            raise self._diagnostic(node, exc)
        except (ZeroDivisionError, OverflowError, ValueError):
            return None
        if not all(self._is_foldable_result(v) for v in result):
            return None

        return self._vector_to_ast(result, node.code_range, node)
    
    # Comparison operations
    
    def visitLess_N(self, node: Less_N, ast_root_node: Program_N):
        """Fold less-than comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l < r)
    
    def visitGreater_N(self, node: Greater_N, ast_root_node: Program_N):
        """Fold greater-than comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l > r)
    
    def visitLessEqual_N(self, node: LessEqual_N, ast_root_node: Program_N):
        """Fold less-equal comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l <= r)
    
    def visitGreaterEqual_N(self, node: GreaterEqual_N, ast_root_node: Program_N):
        """Fold greater-equal comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l >= r)
    
    def visitEqual_N(self, node: Equal_N, ast_root_node: Program_N):
        """Fold equality comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l == r)
    
    def visitNotEqual_N(self, node: NotEqual_N, ast_root_node: Program_N):
        """Fold not-equal comparison."""
        return self._handle_comparison_op(node, ast_root_node, lambda l, r: l != r)
    
    def _handle_comparison_op(self, node, ast_root_node, comparator):
        """
        Generic handler for comparison operations.
        
        Args:
            node: The comparison operation node
            ast_root_node: Root of the AST
            comparator: Function to perform the comparison
        """
        # Visit children first
        node.left = self.visit(node.left, ast_root_node)
        node.right = self.visit(node.right, ast_root_node)
        
        # Check if both operands are constant literals
        if self._is_constant_literal(node.left) and self._is_constant_literal(node.right):
            try:
                left_val = self._get_literal_value(node.left)
                right_val = self._get_literal_value(node.right)
                result = comparator(left_val, right_val)
                
                # Convert Python boolean result to string for consistency
                result_str = self._bool_to_string(result)
                return self._create_typed_bool_literal(node.code_range, result_str, node)
            except (TypeError, ValueError):
                # Don't fold if comparison fails (e.g., incompatible types)
                pass
        
        return node
    
    # Logical operations
    
    def visitAnd_N(self, node: And_N, ast_root_node: Program_N):
        """Fold logical AND operations."""
        return self._handle_logical_binary_op(node, ast_root_node, lambda l, r: l and r)
    
    def visitOr_N(self, node: Or_N, ast_root_node: Program_N):
        """Fold logical OR operations."""
        return self._handle_logical_binary_op(node, ast_root_node, lambda l, r: l or r)
    
    def _handle_logical_binary_op(self, node, ast_root_node, operator):
        """
        Generic handler for logical binary operations.
        
        Args:
            node: The logical operation node
            ast_root_node: Root of the AST
            operator: Function to perform the logical operation
        """
        # Visit children first
        node.left = self.visit(node.left, ast_root_node)
        node.right = self.visit(node.right, ast_root_node)
        
        # Check if both operands are boolean literals
        if (isinstance(node.left, BoolLiteral_N) and 
            isinstance(node.right, BoolLiteral_N)):
            # Convert string boolean values to Python booleans
            left_bool = self._string_to_bool(node.left.value)
            right_bool = self._string_to_bool(node.right.value)
            result = operator(left_bool, right_bool)
            # Convert result back to string for consistency with GeLB AST
            result_str = self._bool_to_string(result)
            return self._create_typed_bool_literal(node.code_range, result_str, node)
        
        return node
    
    # Unary operations
    
    def visitNotExpr_N(self, node: NotExpr_N, ast_root_node: Program_N):
        """Fold logical NOT operations."""
        node.value = self.visit(node.value, ast_root_node)
        
        if isinstance(node.value, BoolLiteral_N):
            # Convert string boolean to Python boolean, apply NOT, convert back
            bool_val = self._string_to_bool(node.value.value)
            result = not bool_val
            result_str = self._bool_to_string(result)
            return self._create_typed_bool_literal(node.code_range, result_str, node.value)
        
        return node
    
    def visitUnaryMinusExpr_N(self, node: UnaryMinusExpr_N, ast_root_node: Program_N):
        """Fold unary minus operations, in the operand's width: negating
        the minimum integer of a width is an overflow."""
        node.value = self.visit(node.value, ast_root_node)

        if isinstance(node.value, (IntLiteral_N, RealLiteral_N)):
            try:
                value = plain(negate(typed_literal_value(node.value)))
            except ConstantEvaluationError as exc:
                raise self._diagnostic(node, exc)
            if isinstance(node.value, IntLiteral_N):
                return self._create_typed_int_literal(node.code_range, value, node.value)
            return self._create_typed_real_literal(node.code_range, value, node.value)

        return node

    @staticmethod
    def _diagnostic(node, exc):
        """The compile-time error the numerical semantics make of ``exc``
        (an integer overflow; an invalid real-to-integer conversion), at
        the expression's location."""
        return GeLBExTypeError(
            node,
            f"{exc} in a constant expression",
            "An integer overflow and a real-to-integer conversion of a NaN, an"
            " infinity or an out-of-range value are compile-time errors in a"
            " constant expression (user manual, numerical semantics chapter); change the"
            " operands or their type.")

    @staticmethod
    def _is_foldable_result(value):
        """A value the folder writes into a literal: any value the
        evaluator returned, an infinity or a NaN included (the backends
        emit those as explicit special values)."""
        return value is not None
    
    # Helper methods
    
    def _is_constant_literal(self, node):
        """Check if a node is a constant literal that can be folded.

        Unwraps any ``TypePromotionNode_N`` first -- the type-checker
        wraps numeric literals to record an explicit-precision
        promotion (e.g. ``int -> real`` when an ``int`` operand sits
        next to a ``real`` operand in a ``Mul_N``).  Without the
        unwrap, expressions like ``DA * NY * NY`` (where ``DA`` is
        real and ``NY`` is int) would never fold past the first
        multiplication: the promoted ``NY`` would be flagged as
        non-literal and the visitor would bail.  Downstream fold of
        ``sqrt(K_PERM)`` then leaves ``std::sqrt(g_K_PERM)`` in the
        emit, which gcc tolerates as a non-strict ``constexpr``
        extension but nvcc rejects with "expression must have a
        constant value" (``std::sqrt`` is not ``constexpr`` until
        C++26).
        """
        node = self._unwrap_promotion(node)
        return (isinstance(node, IntLiteral_N) or
                isinstance(node, RealLiteral_N) or
                isinstance(node, BoolLiteral_N))

    def _get_literal_value(self, node):
        """Extract the Python value from a literal node, *after* the
        conversions its ``TypePromotionNode_N`` wrappers record (paired
        with the unwrap in ``_is_constant_literal``): the integer in
        ``16777217 == real32(16777216)`` is promoted to real32 before
        the comparison, which rounds it to 16777216; the converted
        values are what the fold compares.
        """
        promotions = []
        while isinstance(node, TypePromotionNode_N):
            promotions.append(node.target_type)
            node = node.expr
        if isinstance(node, (IntLiteral_N, RealLiteral_N)):
            value = typed_literal_value(node)     # in the literal's width
        elif isinstance(node, BoolLiteral_N):
            # Convert GeLB boolean string to Python boolean for comparisons
            value = self._string_to_bool(node.value)
        else:
            raise ValueError(f"Not a literal node: {type(node)}")
        for target in reversed(promotions):
            value = self._promoted(value, target)
        return value

    def _promoted(self, value, target_type):
        """``value`` after the conversion a ``TypePromotionNode_N`` to
        ``target_type`` records, carrying the target's width."""
        dtype = self._element_dtype(target_type)
        return value if dtype is None else convert(value, dtype)

    # --- declared widths ---
    #
    # A folded value takes the width of the node it replaces: a real32
    # constant, cast or arithmetic result is rounded to binary32, an int32
    # one wraps.  The literal then means the same at compile time (a paint
    # predicate evaluates it), in the generated code (the backends emit
    # the rounded payload, which the target compiler rounds to the same
    # value) and when it is widened again (real(real32(16777217.0)) is
    # 16777216.0, not 16777217.0).

    @staticmethod
    def _element_dtype(node_or_type):
        t = getattr(node_or_type, 'inferred_type', node_or_type)
        return getattr(t, 'element_dtype', None)

    @staticmethod
    def _is_narrow(dtype):
        return dtype in NARROW_INT_WIDTHS or dtype in NARROW_REAL_WIDTHS

    @staticmethod
    def _scalar_type(code_range, dtype):
        return ArrayDataType_N(code_range, dtype, List_N(code_range))

    def _narrowed(self, literal, dtype=None):
        """``literal`` with its payload in the width ``dtype`` (default:
        the literal's own inferred width)."""
        dtype = dtype if dtype is not None else self._element_dtype(literal)
        if dtype is not None and isinstance(literal, (IntLiteral_N, RealLiteral_N)):
            literal.value = narrow_scalar(literal.value, dtype)
        return literal

    def _literal_of_width(self, literal, dtype, code_range=None):
        """A new literal holding ``literal``'s value in the width
        ``dtype``, of the kind that width has: an integer written into a
        real slot becomes a real literal, rounded if the width is narrow."""
        code_range = code_range if code_range is not None else literal.code_range
        if dtype in _REAL_WIDTHS:
            new = RealLiteral_N(code_range, float(convert_plain(literal.value, dtype)))
        elif dtype in _INT_WIDTHS:
            # a real payload truncates, and is an error out of range
            new = IntLiteral_N(code_range, int(convert_plain(literal.value, dtype)))
        else:
            return literal
        new.inferred_type = self._scalar_type(code_range, dtype)
        return new

    def _narrow_array_elements(self, array_node, dtype):
        """Rewrite the literal elements of an array literal (1-D or 2-D,
        in place) as literals of the element width ``dtype``, if it is
        narrow: payload, kind and type together."""
        if not self._is_narrow(dtype):
            return array_node
        elements = array_node.value.elements
        for i, elem in enumerate(elements):
            negated = isinstance(elem, UnaryMinusExpr_N)
            target = elem.value if negated else elem
            if isinstance(target, Array1DLiteral_N):
                self._narrow_array_elements(target, dtype)
            elif isinstance(target, (IntLiteral_N, RealLiteral_N)):
                try:
                    new = self._literal_of_width(target, dtype)
                except (OverflowError, ValueError):
                    continue      # not a value the width can take
                if negated:
                    elem.value = new
                else:
                    elements[i] = new
        return array_node

    def _create_literal_from_value(self, value, original_node):
        """
        Create appropriate literal node from a Python value.
        
        Args:
            value: Python value (int, float, bool)
            original_node: Original AST node for code range
            
        Returns:
            Literal_N node or None if value type not supported
        """
        value = plain(value)          # a NumPy scalar as the value it holds
        if isinstance(value, bool):
            # Convert Python boolean to GeLB boolean string
            bool_str = self._bool_to_string(value)
            result = BoolLiteral_N(original_node.code_range, bool_str)
        elif isinstance(value, int):
            result = IntLiteral_N(original_node.code_range, value)
        elif isinstance(value, float):
            result = RealLiteral_N(original_node.code_range, value)
        else:
            return None
        
        # Preserve ArrayDataType_N inferred_type if available
        self._preserve_inferred_type(result, original_node)
        return self._narrowed(result)
    
    def _preserve_inferred_type(self, new_literal, original_node):
        """
        Preserve the inferred_type from the original node to the new literal.
        
        This is crucial for maintaining ArrayDataType_N consistency after constant folding.
        The original node should have an inferred_type set by TypeInferenceVisitor.
        """
        if hasattr(original_node, 'inferred_type'):
            new_literal.inferred_type = original_node.inferred_type
        else:
            # Fallback: create appropriate ArrayDataType_N based on literal type
            self._set_default_array_type(new_literal)
    
    def _set_default_array_type(self, literal_node):
        """Set default ArrayDataType_N for a literal node."""
        if isinstance(literal_node, IntLiteral_N):
            element_dtype = "int"
        elif isinstance(literal_node, RealLiteral_N):
            element_dtype = "real"
        elif isinstance(literal_node, BoolLiteral_N):
            element_dtype = "bool"
        else:
            return  # Unknown type, skip
        
        # Create 0-dimensional array type (scalar as array)
        empty_shape = List_N(literal_node.code_range)
        literal_node.inferred_type = ArrayDataType_N(literal_node.code_range, element_dtype, empty_shape)
    
    def _create_typed_bool_literal(self, code_range, bool_str, reference_node=None):
        """Create a BoolLiteral_N with proper ArrayDataType_N type."""
        result = BoolLiteral_N(code_range, bool_str)
        if reference_node and hasattr(reference_node, 'inferred_type'):
            result.inferred_type = reference_node.inferred_type
        else:
            self._set_default_array_type(result)
        return result
    
    def _create_typed_int_literal(self, code_range, value, reference_node=None):
        """Create an IntLiteral_N with proper ArrayDataType_N type."""
        result = IntLiteral_N(code_range, value)
        if reference_node and hasattr(reference_node, 'inferred_type'):
            result.inferred_type = reference_node.inferred_type
        else:
            self._set_default_array_type(result)
        return self._narrowed(result)
    
    def _create_typed_real_literal(self, code_range, value, reference_node=None):
        """Create a RealLiteral_N with proper ArrayDataType_N type."""
        result = RealLiteral_N(code_range, value)
        if reference_node and hasattr(reference_node, 'inferred_type'):
            result.inferred_type = reference_node.inferred_type
        else:
            self._set_default_array_type(result)
        return self._narrowed(result)
    
    # Arithmetic evaluators
    
    # The arithmetic is ast_eval's, the one compile-time evaluator (user
    # manual, Numerical semantics: Types and promotion): the operands
    # are the literals' values in their widths, with the conversions
    # their promotion wrappers record applied, so the converted values
    # decide whether a division is an integer division.

    def _evaluate_add(self, left_node, right_node):
        return add(self._get_literal_value(left_node), self._get_literal_value(right_node))

    def _evaluate_sub(self, left_node, right_node):
        return sub(self._get_literal_value(left_node), self._get_literal_value(right_node))

    def _evaluate_mul(self, left_node, right_node):
        return mul(self._get_literal_value(left_node), self._get_literal_value(right_node))

    def _evaluate_div(self, left_node, right_node):
        """Two integers divide as integers, truncating toward zero;
        any other combination is a real division.  A zero divisor raises
        ZeroDivisionError for the validator to report."""
        return divide(self._get_literal_value(left_node), self._get_literal_value(right_node))

    def _evaluate_pow(self, left_node, right_node):
        """Exact integer arithmetic for an integer base and exponent, with
        Fortran's rule for a negative exponent; the host's pow for a
        real base."""
        return power(self._get_literal_value(left_node), self._get_literal_value(right_node))
    
    # Block traversal (from mixin)
    
    def visitGlobalConstantsBlock_N(self, node: GlobalConstantsBlock_N, ast_root_node: Program_N):
        """Process statements in global constants block."""
        return self._rewrite_block_stmts(node, ast_root_node)
    
    def visitInitializerBlock_N(self, node: InitializerBlock_N, ast_root_node: Program_N):
        """Process statements in initializer block."""
        return self._rewrite_block_stmts(node, ast_root_node)
    
    def visitDynamicBlock_N(self, node: DynamicBlock_N, ast_root_node: Program_N):
        """Process statements in dynamic block."""
        return self._rewrite_block_stmts(node, ast_root_node)
    
    def visitGaugeBlock_N(self, node: GaugeBlock_N, ast_root_node: Program_N):
        """Process statements in gauge block."""
        return self._rewrite_block_stmts(node, ast_root_node)

    def visitFunctionBlock_N(self, node, ast_root_node: Program_N):
        """Process statements in function block."""
        return self._rewrite_block_stmts(node, ast_root_node)

    def visitGeometryBlock_N(self, node: GeometryBlock_N, ast_root_node: Program_N):
        """Process statements in geometry block."""
        return self._rewrite_block_stmts(node, ast_root_node)
    
    # Pass-through for blocks that don't contain expressions
    
    def visitLatticesBlock_N(self, node: LatticesBlock_N, ast_root_node: Program_N):
        """Lattices block may contain expressions in lattice instantiation."""
        return self._rewrite_block_stmts(node, ast_root_node)
    
    def visitNodeClassesBlock_N(self, node: NodeClassesBlock_N, ast_root_node: Program_N):
        """Node classes block doesn't contain expressions to fold."""
        return node
    
    # Statement processing
    
    def visitConstantDefinitionStmt_N(self, node: ConstantDefinitionStmt_N, ast_root_node: Program_N):
        """Fold expressions in constant definitions."""
        node.value = self.visit(node.value, ast_root_node)
        return node
    
    def visitVariableAssignmentStmt_N(self, node: VariableAssignmentStmt_N, ast_root_node: Program_N):
        """Fold expressions in variable assignments."""
        node.lhs = self.visit(node.lhs, ast_root_node)
        node.rhs = self.visit(node.rhs, ast_root_node)
        return node
    
    def visitLatticeOutSelectionAssignmentStmt_N(self, node: LatticeOutSelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Fold expressions in lattice assignments."""
        node.lhs = self.visit(node.lhs, ast_root_node)
        node.rhs = self.visit(node.rhs, ast_root_node)
        return node
    
    def visitArraySelectionAssignmentStmt_N(self, node: ArraySelectionAssignmentStmt_N, ast_root_node: Program_N):
        """Fold expressions in array assignments."""
        node.lhs = self.visit(node.lhs, ast_root_node)
        node.rhs = self.visit(node.rhs, ast_root_node)
        return node
    
    def visitLatticeInstaStmt_N(self, node: LatticeInstaStmt_N, ast_root_node: Program_N):
        """Fold expressions in lattice instantiation."""
        if node.d is not None:
            node.d = self.visit(node.d, ast_root_node)
        if node.q is not None:
            node.q = self.visit(node.q, ast_root_node)
        if hasattr(node, 'grid_size') and node.grid_size is not None:
            node.grid_size = self.visit(node.grid_size, ast_root_node)
        if hasattr(node, 'periodicity') and node.periodicity is not None:
            node.periodicity = self.visit(node.periodicity, ast_root_node)
        return node
    
    def visitPaintNodesStmt_N(self, node: PaintNodesStmt_N, ast_root_node: Program_N):
        """Process paint statements."""
        if node.lhs is not None:
            node.lhs = self.visit(node.lhs, ast_root_node)
        return node

    def visitBorderStmt_N(self, node, ast_root_node):
        return node  # No expressions to fold

    def visitConditionalPaintStmt_N(self, node, ast_root_node):
        node.predicate = self.visit(node.predicate, ast_root_node)
        return node

    def visitRange_N(self, node: Range_N, ast_root_node: Program_N):
        """Fold expressions in range bounds."""
        if node.low is not None:
            node.low = self.visit(node.low, ast_root_node)
        if node.high is not None:
            node.high = self.visit(node.high, ast_root_node)
        return node
    
    def visitList_N(self, node: List_N, ast_root_node: Program_N):
        """Process all elements in a list."""
        for i, elem in enumerate(node.elements):
            node.elements[i] = self.visit(elem, ast_root_node)
        return node
    
    # Array literals
    
    def visitArray1DLiteral_N(self, node: Array1DLiteral_N, ast_root_node: Program_N):
        """Fold expressions in 1D array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def visitArray2DLiteral_N(self, node: Array2DLiteral_N, ast_root_node: Program_N):
        """Fold expressions in 2D array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def visitArray3DLiteral_N(self, node: Array3DLiteral_N, ast_root_node: Program_N):
        """Fold expressions in 3D array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def visitArray4DLiteral_N(self, node: Array4DLiteral_N, ast_root_node: Program_N):
        """Fold expressions in 4D array literals."""
        return self._handle_array_literal(node, ast_root_node)
    
    def _handle_array_literal(self, node, ast_root_node):
        """Fold expressions within array literals."""
        if hasattr(node, 'value') and hasattr(node.value, 'elements'):
            for i, elem in enumerate(node.value.elements):
                node.value.elements[i] = self.visit(elem, ast_root_node)
        return node

    # Intrinsic function calls

    def visitIntrinsicFunctionCall_N(self, node, ast_root_node: Program_N):
        """Fold intrinsic function calls when all arguments are compile-time constants."""
        for i, arg in enumerate(node.arguments.elements):
            node.arguments.elements[i] = self.visit(arg, ast_root_node)

        result = self._try_evaluate_intrinsic(node)
        return result if result is not None else node

    def _try_evaluate_intrinsic(self, node):
        """Evaluate an intrinsic at compile time.  Returns folded node or None."""
        name = node.function_name
        args = node.arguments.elements

        # Matrix intrinsics (SymPy)
        if name == 'inverse':
            return self._try_fold_inverse(node, args)
        elif name == 'determinant':
            return self._try_fold_determinant(node, args)
        elif name == 'transpose' and len(args) == 1:
            return self._try_fold_transpose(node, args)
        elif name == 'matmul' and len(args) == 2:
            return self._try_fold_matmul(node, args)

        # Reduction intrinsics
        elif name == 'sum' and len(args) == 1:
            return self._try_fold_sum(node, args)
        elif name == 'dot_prod' and len(args) == 2:
            return self._try_fold_dot_prod(node, args)

        # Scalar intrinsics: ast_eval's, the one evaluator
        elif name in SCALAR_INTRINSICS:
            return self._try_fold_scalar_intrinsic(node, name, args)

        # Type-cast intrinsics
        elif name in CAST_INTRINSIC_NAMES and len(args) == 1:
            return self._try_fold_cast(node, name, args[0])

        return None  # Not foldable (random, streaming intrinsics, etc.)

    def _try_fold_cast(self, node, target_name, arg):
        """Fold a type-cast intrinsic on a constant argument.

        Returns a new IntLiteral_N or RealLiteral_N if foldable, else
        None.  Truncates real -> int toward zero (Fortran semantics).
        Bool -> numeric: true -> 1, false -> 0.
        """
        # Unwrap implicit promotion wrappers around the argument
        inner = self._unwrap_promotion(arg)

        if isinstance(inner, BoolLiteral_N):
            value = inner.value == 'true'
        elif self._is_foldable_scalar(arg):
            value = self._scalar_value(arg)
        else:
            return None
        # The conversion is ast_eval's: an integer to a narrower
        # integer wraps, a real to an integer truncates and is an error
        # for a NaN or out of range, an integer to real32 rounds once,
        # directly (through binary64 it could round twice).
        try:
            converted = plain(convert(value, target_name))
        except ConstantEvaluationError as exc:
            raise self._diagnostic(node, exc)
        except (OverflowError, ValueError):
            # not a conversion the evaluator performs here (in the IEEE
            # mode a real narrowed past its range is an infinity)
            return None
        if target_name in INT_CAST_NAMES:
            lit = IntLiteral_N(node.code_range, int(converted))
        else:
            lit = RealLiteral_N(node.code_range, float(converted))
        if hasattr(node, 'inferred_type'):
            lit.inferred_type = node.inferred_type
        else:
            self._set_default_array_type(lit)
        return lit

    # --- Array helpers ---

    def _is_constant_array(self, node):
        """Check if node is an array literal with all-constant leaf elements."""
        if isinstance(node, TypePromotionNode_N):
            return self._is_constant_array(node.expr)
        if isinstance(node, Array1DLiteral_N):
            return all(self._is_foldable_scalar(e) for e in node.value.elements)
        if isinstance(node, Array2DLiteral_N):
            return all(
                self._is_constant_array(row)
                for row in node.value.elements
            )
        return False

    def _is_foldable_scalar(self, node):
        """Check if node is a scalar constant (literal or negated literal)."""
        if isinstance(node, TypePromotionNode_N):
            return self._is_foldable_scalar(node.expr)
        if isinstance(node, (IntLiteral_N, RealLiteral_N)):
            return True
        if isinstance(node, UnaryMinusExpr_N):
            return self._is_foldable_scalar(node.value)
        return False

    def _scalar_value(self, node):
        """The value of a scalar constant node in its width, with the
        conversions its promotion wrappers record applied."""
        if isinstance(node, TypePromotionNode_N):
            return self._promoted(self._scalar_value(node.expr),
                                  node.target_type)
        if isinstance(node, (IntLiteral_N, RealLiteral_N)):
            return typed_literal_value(node)
        if isinstance(node, UnaryMinusExpr_N):
            return negate(self._scalar_value(node.value))
        raise ValueError(f"Not a scalar constant: {type(node).__name__}")

    def _unwrap_promotion(self, node):
        """Unwrap TypePromotionNode_N wrappers."""
        while isinstance(node, TypePromotionNode_N):
            node = node.expr
        return node

    def _extract_vector(self, node):
        """Extract Python list from Array1DLiteral_N; a promotion of the
        whole array (an ``array[real32, q]`` constant written with plain
        literals) converts every element."""
        promotions = []
        while isinstance(node, TypePromotionNode_N):
            promotions.append(node.target_type)
            node = node.expr
        values = [self._scalar_value(e) for e in node.value.elements]
        for target in reversed(promotions):
            values = [self._promoted(v, target) for v in values]
        # plain values: the reductions and the matrix intrinsics compute
        # in binary64 on them (the SymPy matrices must not see a NumPy
        # float32, which would set their precision to 24 bits)
        return [plain(v) for v in values]

    def _typed_vector(self, node, dtype):
        """``_extract_vector`` with every element in the array's element
        width ``dtype``, for the element-wise fold.  A value past the
        width's range raises OverflowError, which every caller treats
        as "not folded"."""
        values = self._extract_vector(node)
        return values if dtype is None else [convert(v, dtype) for v in values]

    def _extract_matrix(self, node):
        """Extract nested Python list from Array2DLiteral_N, promotions
        of the whole matrix applied to every element."""
        promotions = []
        while isinstance(node, TypePromotionNode_N):
            promotions.append(node.target_type)
            node = node.expr
        rows = [self._extract_vector(row) for row in node.value.elements]
        for target in reversed(promotions):
            rows = [[plain(self._promoted(v, target)) for v in row] for row in rows]
        return rows

    def _make_real_literal(self, value, code_range, ref_node=None):
        """Create a RealLiteral_N with proper inferred_type."""
        lit = RealLiteral_N(code_range, float(value))
        if ref_node and hasattr(ref_node, 'inferred_type'):
            lit.inferred_type = ref_node.inferred_type
        else:
            self._set_default_array_type(lit)
        return self._narrowed(lit)

    def _element_literal(self, value, code_range, dtype):
        """A literal element of an array of element width ``dtype``:
        an integer literal for an integer width, else a real one."""
        value = plain(value)
        if dtype in _INT_WIDTHS:
            lit = IntLiteral_N(code_range, int(value))
        else:
            lit = RealLiteral_N(code_range, float(value))
        self._set_default_array_type(lit)
        return lit

    @staticmethod
    def _all_finite(values):
        return all(not (isinstance(v, float) and not math.isfinite(v))
                   for v in (plain(x) for x in values))

    def _matrix_to_ast(self, rows, code_range, ref_node):
        """An Array2DLiteral_N from nested lists of values, elements in
        the node's width (an infinity or a NaN written as such)."""
        dtype = self._element_dtype(ref_node)
        outer = List_N(code_range)
        for row in rows:
            inner = List_N(code_range)
            for v in row:
                inner.append(self._element_literal(v, code_range, dtype))
            outer.append(Array1DLiteral_N(code_range, inner))
        result = Array2DLiteral_N(code_range, outer)
        if hasattr(ref_node, 'inferred_type'):
            result.inferred_type = ref_node.inferred_type
        return self._narrow_array_elements(result, dtype)

    def _vector_to_ast(self, values, code_range, ref_node):
        """An Array1DLiteral_N from a list of values, elements in the
        node's width (an infinity or a NaN written as such)."""
        dtype = self._element_dtype(ref_node)
        inner = List_N(code_range)
        for v in values:
            inner.append(self._element_literal(v, code_range, dtype))
        result = Array1DLiteral_N(code_range, inner)
        if hasattr(ref_node, 'inferred_type'):
            result.inferred_type = ref_node.inferred_type
        return self._narrow_array_elements(result, dtype)

    @staticmethod
    def _sympy_rows(sp_matrix):
        rows, cols = sp_matrix.shape
        return [[float(sp_matrix[i, j]) for j in range(cols)] for i in range(rows)]

    def _matrix_diagnostic(self, node, what):
        return GeLBExTypeError(
            node,
            f"{what} of a constant matrix is not finite",
            "The result cannot be written as a constant and the backends"
            " have no run-time form for it; change the matrix.")

    # --- Matrix fold methods (SymPy) ---

    def _matrix_data(self, node, arg):
        """The matrix's entries as the values its declared width holds
        (a real32 matrix's entries are the binary32 roundings), in
        binary64 for SymPy; or the diagnostic for an entry the width
        cannot hold, or that is not finite (the matrix intrinsics have
        no run-time form on the C++ backends and SymPy has no IEEE
        arithmetic, so nothing is left to run time)."""
        try:
            rows = [[plain(v) for v in row] for row in self._typed_matrix(arg)]
        except (OverflowError, ValueError) as exc:
            raise GeLBExTypeError(
                node,
                f"{exc} in a constant matrix",
                "An element of the matrix is outside its declared width;"
                " change the element or the width.")
        if not all(self._all_finite(row) for row in rows):
            raise GeLBExTypeError(
                node,
                "an infinite or NaN element in a constant matrix",
                "An element of the matrix is outside its declared width"
                " or is not a number; change the element or the width.")
        return rows

    def _try_fold_inverse(self, node, args):
        if len(args) != 1 or not self._is_constant_array(args[0]):
            return None
        import sympy
        data = self._matrix_data(node, args[0])
        sp = sympy.Matrix(data)
        try:
            sp_inv = sp.inv()
        except sympy.matrices.common.NonInvertibleMatrixError:
            raise GeLBException(
                f"Singular matrix at {node.code_range}: "
                f"cannot compute inverse (determinant is zero)",
                "Check that the matrix passed to inverse() is non-singular"
            )
        result = self._matrix_to_ast(self._sympy_rows(sp_inv), node.code_range, node)
        if result is None:
            raise self._matrix_diagnostic(node, "The inverse")
        return result

    def _try_fold_determinant(self, node, args):
        if len(args) != 1 or not self._is_constant_array(args[0]):
            return None
        import sympy
        data = self._matrix_data(node, args[0])
        det_val = float(sympy.Matrix(data).det())
        if not math.isfinite(det_val):
            raise self._matrix_diagnostic(node, "The determinant")
        return self._make_real_literal(det_val, node.code_range, node)

    def _try_fold_transpose(self, node, args):
        if not self._is_constant_array(args[0]):
            return None
        if not isinstance(args[0], Array2DLiteral_N):
            return None
        import sympy
        data = self._matrix_data(node, args[0])
        sp_t = sympy.Matrix(data).T
        return self._matrix_to_ast(self._sympy_rows(sp_t), node.code_range, node)

    def _try_fold_matmul(self, node, args):
        """``matmul`` of constants, each product and each sum in the
        element width (an infinity or a NaN written as such)."""
        a, b = (self._constant_array_literal(x) for x in args)
        if not isinstance(a, Array2DLiteral_N) or b is None:
            return None
        try:
            ra = self._typed_matrix(a)
            if isinstance(b, Array2DLiteral_N):
                rb = self._typed_matrix(b)
                if not ra or not rb or len(ra[0]) != len(rb):
                    return None
                rows = [[self._sum([mul(ra[i][k], rb[k][j]) for k in range(len(rb))])
                         for j in range(len(rb[0]))] for i in range(len(ra))]
                return self._matrix_to_ast(rows, node.code_range, node)
            if isinstance(b, Array1DLiteral_N):
                vb = self._typed_vector(b, self._element_dtype(b))
                if not ra or len(ra[0]) != len(vb):
                    return None
                flat = [self._sum([mul(ra[i][k], vb[k]) for k in range(len(vb))])
                        for i in range(len(ra))]
                return self._vector_to_ast(flat, node.code_range, node)
        except ConstantEvaluationError as exc:
            raise self._diagnostic(node, exc)
        except (OverflowError, ValueError):
            return None
        return None

    # --- Reduction fold methods ---
    #
    # A reduction of constants is evaluated term by term with the one
    # evaluator, in the expression's width: an integer sum is exact and
    # its overflow an error, a real32 dot product rounds each product
    # and each sum to binary32, an overflow is the infinity the run
    # time would give.  The array may be written inline or be a named
    # constant; the folder keeps array constants named elsewhere, so
    # the lookup is local to these folds.

    def _constant_definition(self, name):
        """The ``ConstantDefinitionStmt_N`` the name denotes in the
        current block's scope, or None."""
        block = getattr(self, 'current_block', None)
        symbol_table = getattr(block, 'symbol_defs', None) if block is not None else None
        if symbol_table is None:
            return None
        symbol_def = symbol_table.get_symbol_definition(name)
        if symbol_def is None and getattr(symbol_table, 'parent_table', None):
            symbol_def = symbol_table.parent_table.get_symbol_definition(name)
        if symbol_def and symbol_def.tag in ('constant', 'constant definition') \
                and hasattr(symbol_def.value, 'value'):
            return symbol_def.value
        return None

    def _constant_array_literal(self, node):
        """The literal array ``node`` denotes: a literal of constants
        (promotions of the whole array kept on it), or the value of a
        named constant array, typed by its declaration.  None otherwise."""
        if self._is_constant_array(node):
            return node
        if isinstance(node, Identifier_N):
            const_stmt = self._constant_definition(node.name)
            if const_stmt is None:
                return None
            val = const_stmt.value
            while isinstance(val, TypePromotionNode_N):
                val = val.expr
            if isinstance(val, (Array1DLiteral_N, Array2DLiteral_N)) \
                    and self._is_constant_array(val):
                literal = copy.deepcopy(val)
                literal.inferred_type = getattr(const_stmt, 'data_type', None)
                return literal
        return None

    def _typed_matrix(self, node):
        dtype = self._element_dtype(node)
        rows = self._extract_matrix(node)
        return rows if dtype is None else [[convert(v, dtype) for v in row] for row in rows]

    @staticmethod
    def _sum(values):
        """The values added left to right, each addition in its width."""
        total = values[0]
        for v in values[1:]:
            total = add(total, v)
        return total

    def _fold_reduction(self, node, compute):
        """A literal of the reduction's kind and width from
        ``compute()``, or None where the evaluator cannot compute it."""
        try:
            result = compute()
        except ConstantEvaluationError as exc:
            raise self._diagnostic(node, exc)
        except (OverflowError, ValueError, ZeroDivisionError):
            return None
        if not self._is_foldable_result(result):
            return None
        return self._folded_scalar_intrinsic(result, node)

    def _try_fold_sum(self, node, args):
        arr = self._constant_array_literal(args[0])
        if not isinstance(arr, Array1DLiteral_N):
            return None
        if not arr.value.elements:
            return None

        def compute():
            return self._sum(self._typed_vector(arr, self._element_dtype(arr)))
        return self._fold_reduction(node, compute)

    def _try_fold_dot_prod(self, node, args):
        a, b = (self._constant_array_literal(x) for x in args)
        if not (isinstance(a, Array1DLiteral_N) and isinstance(b, Array1DLiteral_N)):
            return None
        if not a.value.elements or len(a.value.elements) != len(b.value.elements):
            return None

        def compute():
            va = self._typed_vector(a, self._element_dtype(a))
            vb = self._typed_vector(b, self._element_dtype(b))
            return self._sum([mul(x, y) for x, y in zip(va, vb)])
        return self._fold_reduction(node, compute)

    # --- Scalar fold methods ---

    def _try_fold_scalar_intrinsic(self, node, name, args):
        """Fold a scalar intrinsic of constant arguments with ast_eval
        (integer mod, min, max and abs are exact; the library
        functions use the host's binary64 library on the arguments'
        rounded values, and a domain error or an overflow is the IEEE
        value).  mod by a visible zero is left for the validator."""
        if not all(self._is_foldable_scalar(a) for a in args):
            return None
        values = [self._scalar_value(a) for a in args]
        try:
            result = intrinsic(name, values)
        except ConstantEvaluationError as exc:
            raise self._diagnostic(node, exc)
        except (ZeroDivisionError, ValueError, OverflowError):
            return None
        if not self._is_foldable_result(result):
            return None
        return self._folded_scalar_intrinsic(result, node)

    def _folded_scalar_intrinsic(self, value, node):
        """A literal for a folded scalar intrinsic, of the kind and width
        the call has: ``abs`` of an integer and ``min`` of two
        integers are integer literals; ``sqrt`` of a ``real32`` is a
        ``real32`` literal, its payload rounded to binary32."""
        dtype = self._element_dtype(node)
        value = plain(value)
        if dtype in _INT_WIDTHS:
            lit = IntLiteral_N(node.code_range, int(value))
            lit.inferred_type = node.inferred_type
            return self._narrowed(lit)
        return self._make_real_literal(value, node.code_range, node)

    def visitUserFunctionCall_N(self, node, ast_root_node: Program_N):
        """Fold constant sub-expressions within user function call arguments."""
        for i, arg in enumerate(node.arguments.elements):
            node.arguments.elements[i] = self.visit(arg, ast_root_node)
        return node

    def visitDestructuringAssignmentStmt_N(self, node, ast_root_node: Program_N):
        """Fold constant sub-expressions in destructuring assignment."""
        node.rhs = self.visit(node.rhs, ast_root_node)
        return node

    # Terminal nodes (no folding needed)
    
    def visitIntLiteral_N(self, node: IntLiteral_N, ast_root_node: Program_N):
        """Integer literals are already constants."""
        return node
    
    def visitRealLiteral_N(self, node: RealLiteral_N, ast_root_node: Program_N):
        """Real literals are already constants."""
        return node
    
    def visitBoolLiteral_N(self, node: BoolLiteral_N, ast_root_node: Program_N):
        """Boolean literals are already constants."""
        return node
    
    def visitStringLiteral_N(self, node: StringLiteral_N, ast_root_node: Program_N):
        """String literals are already constants."""
        return node
    
    def visitIdentifier_N(self, node: Identifier_N, ast_root_node: Program_N):
        """Replace constant identifiers with their literal values for constant propagation."""
        # Check if this identifier refers to a constant
        if hasattr(self, 'current_block') and self.current_block is not None:
            symbol_table = getattr(self.current_block, 'symbol_defs', None)
            # NOTE: must test for None, not truthiness -- SymbolsTable.__len__
            # counts only LOCAL symbols, so a block with an empty local scope
            # (e.g. geometry, whose constants live in the parent table) would
            # falsely test as "no symbol table" and skip hierarchical lookup.
            if symbol_table is not None:
                symbol_def = symbol_table.get_symbol_definition(node.name)
                # Try parent table if not found locally
                if symbol_def is None and hasattr(symbol_table, 'parent_table') and symbol_table.parent_table:
                    symbol_def = symbol_table.parent_table.get_symbol_definition(node.name)
                
                # If it's a constant, return its value
                if symbol_def and symbol_def.tag in ['constant', 'constant definition']:
                    const_stmt = symbol_def.value
                    if hasattr(const_stmt, 'value'):
                        val = const_stmt.value
                        # Unwrap TypePromotionNode_N (from explicit-precision types)
                        while isinstance(val, TypePromotionNode_N):
                            val = val.expr
                        # A constant is its declared type's value, not
                        # its initializer's payload: the wrapper just
                        # unwrapped was the conversion to that type.  So
                        # `const real C = 7` propagates as the real 7.0
                        # (an int literal there would fold `C / E` as an
                        # integer division), and a narrow width rounds
                        # or wraps.
                        declared = getattr(const_stmt, 'data_type', None)
                        dtype = self._element_dtype(declared)
                        if (dtype in _REAL_WIDTHS or dtype in _INT_WIDTHS) and \
                                isinstance(val, (IntLiteral_N, RealLiteral_N)):
                            try:
                                new_literal = self._literal_of_width(
                                    val, dtype, node.code_range)
                            except ConstantEvaluationError as exc:
                                raise self._diagnostic(const_stmt, exc)
                            except (OverflowError, ValueError):
                                # ``const real32 R = 1.0e300;``: the
                                # value is an infinity at run time;
                                # the name stays, the backend
                                # converts
                                return node
                            new_literal.inferred_type = declared
                            return new_literal
                        if isinstance(val, IntLiteral_N):
                            new_literal = IntLiteral_N(node.code_range, val.value)
                            new_literal.inferred_type = val.inferred_type if hasattr(val, 'inferred_type') else None
                            return new_literal
                        elif isinstance(val, RealLiteral_N):
                            new_literal = RealLiteral_N(node.code_range, val.value)
                            new_literal.inferred_type = val.inferred_type if hasattr(val, 'inferred_type') else None
                            return new_literal
                        elif isinstance(val, BoolLiteral_N):
                            new_literal = BoolLiteral_N(node.code_range, val.value)
                            new_literal.inferred_type = val.inferred_type if hasattr(val, 'inferred_type') else None
                            return new_literal
                        elif isinstance(val, (Array1DLiteral_N, Array2DLiteral_N)):
                            # Only inline array constants in the global
                            # constants block, where compile-time intrinsics
                            # (inverse, determinant, sum, dot_prod) need
                            # literal values for folding.  In runtime blocks
                            # (initializer, dynamic, gauge, function), keep
                            # the named reference -- the backend emits it as
                            # a Fortran 'parameter' and the generated code
                            # is cleaner and avoids temporary-allocation
                            # issues in CUDA device kernels.
                            if getattr(self, '_current_block_type', None) == 'global_constants':
                                new_literal = copy.deepcopy(val)
                                new_literal.code_range = node.code_range
                                # the inlined constant has its declared
                                # type, not the literal's own
                                if declared is not None:
                                    new_literal.inferred_type = declared
                                return self._narrow_array_elements(
                                    new_literal, dtype)
                            return node
        
        # Not a constant or can't be resolved - return as is
        return node
    
    def visitVariableDeclarationStmt_N(self, node: VariableDeclarationStmt_N, ast_root_node: Program_N):
        """Variable declarations don't have expressions to fold."""
        return node
    
    def visitRectSelOfLatticeInDFs_N(self, node: RectSelOfLatticeInDFs_N, ast_root_node: Program_N):
        """Lattice selections don't contain expressions to fold."""
        return node
    
    def visitRectSelOfLatticeOutDFs_N(self, node: RectSelOfLatticeOutDFs_N, ast_root_node: Program_N):
        """Lattice selections don't contain expressions to fold."""
        return node
    
    def visitRectSelOfArrayElems_N(self, node: RectSelOfArrayElems_N, ast_root_node: Program_N):
        """Array selections don't contain expressions to fold."""
        return node
    
    # Type promotion nodes
    
    def visitTypePromotionNode_N(self, node: TypePromotionNode_N, ast_root_node: Program_N):
        """
        Fold the wrapped expression in type promotion nodes.
        
        This allows constant folding to work through type promotions,
        enabling promotion expansion to work more effectively.
        """
        node.expr = self.visit(node.expr, ast_root_node)
        return node
    
    def visitBroadcastNode_N(self, node: BroadcastNode_N, ast_root_node: Program_N):
        """
        Fold the scalar expression in broadcast nodes.
        
        Broadcasting itself cannot be folded (it's a runtime operation),
        but we can fold the scalar expression being broadcast.
        """
        node.scalar_expr = self.visit(node.scalar_expr, ast_root_node)
        return node
    
    # Helper methods for boolean conversion
    
    def _string_to_bool(self, string_value):
        """Convert GeLB boolean string to Python boolean."""
        if string_value == 'true':
            return True
        elif string_value == 'false':
            return False
        else:
            raise ValueError(f"Invalid boolean string: {string_value}")
    
    def _bool_to_string(self, bool_value):
        """Convert Python boolean to GeLB boolean string."""
        return 'true' if bool_value else 'false'
