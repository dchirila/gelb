"""Stage-boundary checks over live AST edges, using explicit traversal stacks."""

from gelb.gelb_ast import ASTNodes as A
from gelb.gelb_ast.CanonicalType import CanonicalType, canonical_from_ast
from gelb.utils.exceptions import GeLBInternalInvariantError


DECLARED = {'constant definition', 'variable declaration', 'output variable declaration',
            'input parameter', 'output parameter', 'constant', 'variable'}
IMPLICIT = {'implicit dimension constant', 'implicit lattice coordinate',
            'implicit timestep variable', 'implicit constant', 'implicit variable'}
NONVALUE = {'lattice instance', 'function', 'initializer', 'dynamic', 'gauge', 'node class', 'lattice'}
PROGRAM_FIELDS = {'simulation_description', 'global_constants', 'lattices', 'initializers',
                  'dynamics', 'gauges', 'functions', 'node_classes', 'geometry'}
NAME_SLOTS = {
    A.InitializerBlock_N: {'name'}, A.DynamicBlock_N: {'name'}, A.GaugeBlock_N: {'name'},
    A.FunctionBlock_N: {'name'}, A.LatticeInstaStmt_N: {'name'},
    A.NodeClassInstaStmt_N: {'name', 'initializer', 'dynamic', 'gauge'},
    A.ConstantDefinitionStmt_N: {'name'}, A.VariableDeclarationStmt_N: {'name'},
    A.UserFunctionCall_N: {'function_name'}, A.RectSelOfLatticeInDFs_N: {'lattice_name'},
    A.RectSelOfLatticeOutDFs_N: {'lattice_name'}, A.RectSelOfArrayElems_N: {'array_name'},
    A.PaintNodesStmt_N: {'rhs'}, A.BorderStmt_N: {'source', 'target'},
    A.ConditionalPaintStmt_N: {'node_class'},
}
SELECTIONS = (A.RectSelOfLatticeInDFs_N, A.RectSelOfLatticeOutDFs_N, A.RectSelOfArrayElems_N)


def _walk(ast):
    stack = [(ast, None, None, False)]
    seen = set()
    while stack:
        node, parent, slot, syntax = stack.pop()
        if not isinstance(node, A.Node_N):
            continue
        key = (id(node), id(parent), slot, syntax)
        if key in seen:
            continue
        seen.add(key)
        yield node, parent, slot, syntax
        if isinstance(node, A.List_N):
            stack.extend((child, parent, slot, syntax) for child in reversed(node.elements))
        else:
            for field in reversed(node.get_children_names()):
                value = getattr(node, field)
                skip = syntax or (isinstance(node, A.ArrayDataType_N) and field == 'shape')
                skip |= isinstance(node, SELECTIONS) and field == 'element_ranges'
                children = value if isinstance(value, (list, tuple)) else (value,)
                stack.extend((child, node, field, skip) for child in reversed(children))


def _symbol_type(symbol):
    if symbol.tag in DECLARED:
        data_type = getattr(symbol.value, 'data_type', None)
        if not isinstance(data_type, A.ArrayDataType_N):
            raise GeLBInternalInvariantError(f'missing declared type for symbol {symbol.name}')
        return data_type.canonical_type
    if symbol.tag in IMPLICIT:
        return CanonicalType('int', ())
    if symbol.tag in NONVALUE:
        return None
    raise GeLBInternalInvariantError(f'unrecognized symbol tag: {symbol.tag}')


def canonicalize_types(ast):
    """Attach canonical types without changing declared shapes or expression types."""
    symbols = []
    for node, _, _, _ in _walk(ast):
        if isinstance(node, A.ArrayDataType_N):
            node.canonical_type = canonical_from_ast(node)
        inferred = getattr(node, 'inferred_type', None)
        if isinstance(inferred, A.ArrayDataType_N):
            inferred.canonical_type = canonical_from_ast(inferred)
            node.canonical_type = inferred.canonical_type
        table = getattr(node, 'symbol_defs', None)
        if table is not None:
            symbols.extend(table)
    for symbol in symbols:
        if symbol.tag in DECLARED:
            _symbol_type(symbol)  # Validate the declared-type slot before attaching metadata.
            data_type = symbol.value.data_type
            data_type.canonical_type = canonical_from_ast(data_type)
        symbol.canonical_type = _symbol_type(symbol)
    return ast


class ASTInvariantValidator:
    @staticmethod
    def check_stage1(ast):
        if not isinstance(ast, A.Program_N) or set(ast.get_children_names()) != PROGRAM_FIELDS:
            raise GeLBInternalInvariantError('unexpected Program_N structural fields')

        def require_type(node, data_type):
            expected = canonical_from_ast(data_type)
            if not isinstance(expected, CanonicalType) or node.canonical_type != expected:
                raise GeLBInternalInvariantError(f'inconsistent canonical type on {type(node).__name__}')
            if data_type.canonical_type != expected:
                raise GeLBInternalInvariantError('inconsistent canonical type on ArrayDataType_N')

        for node, parent, slot, syntax in _walk(ast):
            if isinstance(node.get_children(), set):
                raise GeLBInternalInvariantError(f'unordered children on {type(node).__name__}')
            if isinstance(node, A.ArrayDataType_N):
                require_type(node, node)
            table = getattr(node, 'symbol_defs', None)
            for symbol in table if table is not None else ():
                if symbol.tag in DECLARED:
                    data_type = getattr(symbol.value, 'data_type', None)
                    require_type(data_type, data_type)
                if symbol.canonical_type != _symbol_type(symbol):
                    raise GeLBInternalInvariantError(f'inconsistent canonical type for symbol {symbol.name}')
            if not isinstance(node, A.Expr_N):
                continue
            inferred = getattr(node, 'inferred_type', None)
            string = isinstance(node, A.StringLiteral_N) and parent is ast and slot == 'simulation_description'
            nonvalue = string
            nonvalue |= (isinstance(node, A.UserFunctionCall_N)
                         and isinstance(parent, A.DestructuringAssignmentStmt_N) and slot == 'rhs'
                         and getattr(node, 'function_block', None) is not None
                         and len(node.function_block.outputs) > 1)
            nonvalue |= (isinstance(node, A.Identifier_N) and isinstance(parent, A.IntrinsicFunctionCall_N)
                         and slot == 'arguments' and parent.function_name in ('upstream_dfs', 'bounce_back_dfs')
                         and parent.arguments[0] is node)
            if nonvalue:
                if (node.canonical_type is not None
                        or (inferred is not None and not (string and isinstance(inferred, A.StringType_N)))):
                    raise GeLBInternalInvariantError('computational type on non-value expression')
                continue
            exempt = syntax or (isinstance(node, A.Identifier_N) and slot in NAME_SLOTS.get(type(parent), ()))
            exempt |= (isinstance(node, (A.Array1DLiteral_N, A.Array2DLiteral_N, A.Array3DLiteral_N))
                       and isinstance(parent, (A.Array2DLiteral_N, A.Array3DLiteral_N, A.Array4DLiteral_N))
                       and slot == 'value')
            if exempt and inferred is None:
                if node.canonical_type is not None:
                    raise GeLBInternalInvariantError('canonical type without inferred type')
                continue
            require_type(node, inferred)


check_stage1 = ASTInvariantValidator.check_stage1
