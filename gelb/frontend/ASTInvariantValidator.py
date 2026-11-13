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


    @staticmethod
    def check_stage2(ast):
        """Check live declarations, lexical references and types after midware."""
        from gelb.frontend.SymbolsTable import SymbolsTable
        from gelb.frontend.implicit_symbols import (
            active_coordinate_names, active_dimension_names, dimensionality_from_program,
        )

        def require(ok, message):
            if not ok:
                raise GeLBInternalInvariantError(message)

        def typed(node, data_type):
            expected = canonical_from_ast(data_type)
            require(isinstance(expected, CanonicalType)
                    and node.canonical_type == expected
                    and data_type.canonical_type == expected,
                    f'inconsistent canonical type on {type(node).__name__}')

        def entries(nodes, tag):
            return [(node.name.name, tag, node) for node in nodes or ()]

        def table_matches(table, parent, expected):
            require(isinstance(table, SymbolsTable) and table.parent_table is parent,
                    'invalid symbol table or parent')
            names = [str(symbol.name) for symbol in table]
            want = {name: (tag, value) for name, tag, value in expected}
            require(len(want) == len(expected), 'duplicate declarations in block')
            require(len(names) == len(set(names)) and set(names) == set(want),
                    'symbol table membership differs from live declarations')
            for symbol in table:
                tag, value = want[str(symbol.name)]
                require(symbol.tag == tag, f'incorrect symbol tag: {symbol.name}')
                if value is not None:
                    require(symbol.value is value, f'stale declaration: {symbol.name}')
                elif tag in ('implicit lattice coordinate', 'implicit timestep variable'):
                    require(isinstance(symbol.value, A.Identifier_N)
                            and symbol.value.name == str(symbol.name),
                            f'invalid implicit symbol: {symbol.name}')
                if symbol.tag in DECLARED:
                    typed(symbol.value.data_type, symbol.value.data_type)
                require(symbol.canonical_type == _symbol_type(symbol),
                        f'inconsistent canonical type for symbol {symbol.name}')

        require(isinstance(ast, A.Program_N) and set(ast.get_children_names()) == PROGRAM_FIELDS,
                'unexpected Program_N structural fields')
        functions = (tuple(ast.functions) if ast.functions is not None
                     else getattr(ast, '_inlined_functions', ()))
        require(all(isinstance(func, A.FunctionBlock_N) for func in functions),
                'invalid retained function')
        globals_ = []
        blocks = []
        definitions = ((ast.global_constants, 'constant definition'),
                       (ast.lattices, 'lattice instance'), (ast.node_classes, 'node class'))
        for block, tag in definitions:
            if block is not None:
                globals_.extend(entries(block.stmts, tag))
                blocks.append(block)
        for group, tag in ((functions, 'function'), (ast.initializers, 'initializer'),
                           (ast.dynamics, 'dynamic'), (ast.gauges, 'gauge')):
            globals_.extend(entries(group, tag))
            blocks.extend(group or ())
        if ast.geometry is not None:
            blocks.append(ast.geometry)
        dimension = dimensionality_from_program(ast)
        globals_.extend((name, 'implicit dimension constant', None)
                        for name in active_dimension_names(dimension))
        table_matches(ast.symbol_defs, None, globals_)
        function_names = {func.name.name for func in functions}
        executable = (A.InitializerBlock_N, A.DynamicBlock_N, A.GaugeBlock_N, A.FunctionBlock_N)
        definition_tags = {A.GlobalConstantsBlock_N: 'constant definition',
                           A.LatticesBlock_N: 'lattice instance', A.NodeClassesBlock_N: 'node class'}
        for block in blocks:
            expected = []
            if type(block) in definition_tags:
                expected.extend(entries(block.stmts, definition_tags[type(block)]))
            elif isinstance(block, executable):
                require(not any(isinstance(stmt, A.ConstantDefinitionStmt_N) for stmt in block.stmts),
                        'residual local constant after lowering')
                expected.extend(entries([stmt for stmt in block.stmts
                                         if isinstance(stmt, A.VariableDeclarationStmt_N)],
                                        'variable declaration'))
                if isinstance(block, A.FunctionBlock_N):
                    expected.extend(entries(block.inputs, 'input parameter'))
                    expected.extend(entries(block.outputs, 'output parameter'))
                elif isinstance(block, A.GaugeBlock_N):
                    expected.extend(entries(block.outputs, 'output variable declaration'))
            if isinstance(block, (A.InitializerBlock_N, A.DynamicBlock_N, A.GaugeBlock_N, A.GeometryBlock_N)):
                expected.extend((name, 'implicit lattice coordinate', None)
                                for name in active_coordinate_names(dimension))
                if not isinstance(block, A.GeometryBlock_N):
                    expected.append(('t', 'implicit timestep variable', None))
            table_matches(block.symbol_defs, ast.symbol_defs, expected)
            for node, parent, slot, _ in _walk(block):
                # Only the declaration's name is syntax; selection names and
                # node-class/block/function references are lexical references too.
                own_name = slot == 'name' and type(parent) in NAME_SLOTS
                if isinstance(node, A.Identifier_N) and not own_name:
                    require(block.symbol_defs.get_symbol_definition(node.name) is not None,
                            f'dangling identifier: {node.name}')

        roots = (ast,) + (functions if ast.functions is None else ())
        for root in roots:
            for node, parent, slot, _ in _walk(root):
                require(not isinstance(node.get_children(), set),
                        f'unordered children on {type(node).__name__}')
                for call in getattr(node, 'inline_calls', ()):
                    require(call[0] in function_names, f'missing function: {call[0]}')
                origin = getattr(node, 'inlined_from_call', None)
                if origin:
                    require(origin[0] in function_names, f'missing function: {origin[0]}')
                if isinstance(node, A.UserFunctionCall_N):
                    require(node.function_name.name in function_names,
                            f'missing function: {node.function_name.name}')
                if isinstance(node, A.ArrayDataType_N):
                    typed(node, node)
                if not isinstance(node, A.Expr_N):
                    continue
                inferred = getattr(node, 'inferred_type', None)
                string = isinstance(node, A.StringLiteral_N) and parent is ast and slot == 'simulation_description'
                nonvalue = string or (isinstance(node, A.UserFunctionCall_N)
                    and isinstance(parent, A.DestructuringAssignmentStmt_N) and slot == 'rhs'
                    and getattr(node, 'function_block', None) is not None
                    and len(node.function_block.outputs) > 1)
                nonvalue |= (isinstance(node, A.Identifier_N) and isinstance(parent, A.IntrinsicFunctionCall_N)
                    and slot == 'arguments' and parent.function_name in ('upstream_dfs', 'bounce_back_dfs')
                    and parent.arguments[0] is node)
                if nonvalue:
                    require(node.canonical_type is None and (inferred is None
                            or (string and isinstance(inferred, A.StringType_N))),
                            'computational type on non-value expression')
                elif inferred is not None:
                    typed(node, inferred)


check_stage1 = ASTInvariantValidator.check_stage1
check_stage2 = ASTInvariantValidator.check_stage2
