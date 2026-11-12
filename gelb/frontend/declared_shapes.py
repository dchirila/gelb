"""Resolve declaration extents in their owning scope before type inference."""

from gelb.frontend.ASTInvariantValidator import _walk
from gelb.frontend.TypeInferenceVisitor import TypeInferenceVisitor
from gelb.frontend.implicit_symbols import DIMENSION_CONSTANT_NAMES, allows_dimension_constants
from gelb.gelb_ast import ASTNodes as A
from gelb.midware.ast_eval import collect_lattice_info
from gelb.utils.exceptions import GeLBExTypeError


def resolve_declared_shapes(ast):
    evaluator = TypeInferenceVisitor()
    evaluator._lattice_info = collect_lattice_info(ast) if ast.lattices is not None else {}
    scopes = {}
    for node, parent, _, _ in _walk(ast):
        scope = node if isinstance(node, A.Block_N) else scopes.get(id(parent))
        scopes[id(node)] = scope
        if not isinstance(node, A.ArrayDataType_N):
            continue
        evaluator.current_block = scope
        shape = node.shape.value if isinstance(node.shape, A.Array1DLiteral_N) else node.shape
        extents = [] if shape is None else shape.elements if isinstance(shape, A.List_N) else [shape]
        resolved = []
        for extent in extents:
            if not allows_dimension_constants(scope):
                for part, _, _, _ in _walk(extent):
                    if isinstance(part, A.Identifier_N) and part.name in DIMENSION_CONSTANT_NAMES:
                        raise GeLBExTypeError(part, "Grid dimensions are not available in this array shape",
                                              "Use constants in global and function declarations.")
            size = evaluator._evaluate_size_expression(extent, ast)
            resolved.append(A.IntLiteral_N(extent.code_range, size))
        if len(resolved) == 1:
            node.shape = resolved[0]
        elif resolved:
            values = A.List_N(node.shape.code_range)
            values.elements = resolved
            node.shape = A.Array1DLiteral_N(node.shape.code_range, values)
    return ast
