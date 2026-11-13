"""Validate compile-time constants and selectors before entering midware."""

from gelb.frontend.ASTInvariantValidator import _walk
from gelb.frontend.implicit_symbols import allows_dimension_constants
from gelb.frontend.intrinsic_functions import STATEFUL_INTRINSIC_NAMES
from gelb.gelb_ast import ASTNodes as A
from gelb.midware.ast_eval import collect_lattice_info, eval_const_expr, nonfatal_evaluation, plain, _typed
from gelb.utils.exceptions import GeLBExStencilError, GeLBExTypeError


_DYNAMIC_INTRINSICS = STATEFUL_INTRINSIC_NAMES | {'upstream_dfs', 'bounce_back_dfs'}
_BLOCKS = (A.InitializerBlock_N, A.DynamicBlock_N, A.GaugeBlock_N,
           A.FunctionBlock_N, A.GeometryBlock_N)


def _dynamic_dependency(node):
    if isinstance(node, A.RectSelOfLatticeDFs_N):
        return 'a lattice access'
    if (isinstance(node, A.IntrinsicFunctionCall_N)
            and node.function_name in _DYNAMIC_INTRINSICS):
        return f'{node.function_name}()'
    return None


class StaticSelectorValidator:
    def __init__(self, ast):
        self.ast = ast
        self.lattices = collect_lattice_info(ast) if ast.lattices is not None else {}
        self.functions = {fn.name.name: fn for fn in ast.functions or ()}
        self.function_problems = {}
        self.globals = {stmt.name.name for stmt in ast.global_constants.stmts} \
            if ast.global_constants is not None else set()

    def _function_problem(self, name):
        """Check call graphs iteratively, including bodies whose result is unused."""
        if name in self.function_problems:
            return self.function_problems[name]
        stack, active, done = [(name, False)], set(), set()
        problem = None
        while stack:
            current, leaving = stack.pop()
            if leaving:
                active.remove(current)
                done.add(current)
                continue
            if current in active:
                problem = f"recursive function '{current}'"
                break
            if current in done:
                continue
            fn = self.functions.get(current)
            if fn is None:
                problem = f"unknown function '{current}'"
                break
            active.add(current)
            stack.append((current, True))
            calls = []
            for node, _, _, _ in _walk(fn.stmts):
                problem = _dynamic_dependency(node)
                if problem:
                    break
                if isinstance(node, A.UserFunctionCall_N):
                    calls.append((node.function_name.name, False))
            if problem:
                break
            stack.extend(reversed(calls))
        self.function_problems[name] = problem
        return problem

    @staticmethod
    def _reject(node, context, dependency):
        raise GeLBExTypeError(
            node, f"{context} must be compile-time evaluable; depends on {dependency}",
            "Use literals, constants, and pure calls with constant arguments.")

    def _require_constexpr(self, expr, block, constants, context):
        stack = [expr]
        while stack:
            node = stack.pop()
            if not isinstance(node, A.Node_N):
                continue
            problem = _dynamic_dependency(node)
            if isinstance(node, A.Identifier_N):
                symbol = block.symbol_defs.get_symbol_definition(node.name)
                if node.name in constants or node.name in self.globals:
                    continue
                if (symbol is not None and symbol.tag == 'implicit dimension constant'
                        and allows_dimension_constants(block)):
                    continue
                problem = f"'{node.name}' ({symbol.tag if symbol else 'non-constant name'})"
            if isinstance(node, A.UserFunctionCall_N):
                problem = self._function_problem(node.function_name.name)
            if problem:
                self._reject(node, context, problem)
            if isinstance(node, A.ArrayDataType_N):
                continue
            if isinstance(node, A.Range_N) and getattr(node, 'has_open_high', False):
                stack.append(node.low)  # The synthesized high is the array's extent.
            else:
                stack.extend(reversed(node.get_children()))

    def _df_range(self, node, block, constants):
        bounds = node.element_ranges[-1]
        bindings = _ConstantBindings(constants, self.ast, self.lattices)
        for field in ('low', 'high'):
            expr = getattr(bounds, field)
            if expr is None:
                continue
            self._require_constexpr(expr, block, constants, 'DF selector')
            try:
                with nonfatal_evaluation():
                    value = plain(eval_const_expr(
                        expr, bindings, ast=self.ast, lattice_info=self.lattices))
            except (ValueError, TypeError, KeyError, IndexError, ArithmeticError,
                    GeLBExStencilError, RecursionError):
                self._reject(expr, 'DF selector', 'an index that does not evaluate to an integer')
            if isinstance(value, bool) or not isinstance(value, int):
                self._reject(expr, 'DF selector', 'a non-integer index')
            if not isinstance(expr, A.IntLiteral_N):
                setattr(bounds, field, A.IntLiteral_N(expr.code_range, value))
        q = self.lattices[node.lattice_name.name]['q']
        lo = bounds.low.value if bounds.low is not None else 0
        hi = bounds.high.value if bounds.high is not None else q - 1
        if not 0 <= lo <= hi < q:
            raise GeLBExTypeError(node, f'DF range {lo}:{hi} is outside 0..{q - 1} or reversed',
                                  'Use an ordered range of DFs on this lattice.')

    def validate(self):
        blocks = [node for node, _, _, _ in _walk(self.ast) if isinstance(node, _BLOCKS)]
        blocks.sort(key=lambda block: getattr(block.code_range, 'start_line', 0))
        for block in blocks:
            constants = {}
            for stmt in block.stmts:
                if isinstance(stmt, A.ConstantDefinitionStmt_N):
                    self._require_constexpr(stmt.value, block, constants,
                                            f"Constant '{stmt.name.name}' initializer")
                for node, _, _, _ in _walk(stmt):
                    if isinstance(node, A.RectSelOfLatticeDFs_N):
                        self._df_range(node, block, constants)
                    elif isinstance(node, A.RectSelOfArrayElems_N):
                        for bounds in node.element_ranges:
                            self._require_constexpr(bounds, block, constants, 'Array index')
                if isinstance(stmt, A.ConstantDefinitionStmt_N):
                    constants[stmt.name.name] = stmt
        return self.ast


class _ConstantBindings(dict):
    """Evaluate only constants used by a DF bound, in their declared width."""
    def __init__(self, declarations, ast, lattices):
        super().__init__()
        self.declarations, self.ast, self.lattices = declarations, ast, lattices

    def __contains__(self, name):
        return name in self.declarations

    def __getitem__(self, name):
        if not super().__contains__(name):
            stmt = self.declarations[name]
            self[name] = _typed(eval_const_expr(
                stmt.value, self, ast=self.ast, lattice_info=self.lattices), stmt.data_type)
        return super().__getitem__(name)


def validate_static_selectors(ast):
    return StaticSelectorValidator(ast).validate()
