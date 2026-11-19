"""Backend facts are computed once, with exact values and scoped metadata."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from gelb.compiler_pipeline import (
    PipelineOptions, PipelineProfile, ProgramFacts, compile_source, build_backend_context,
)
from gelb.frontend.SymbolsTable import SymbolsTable
from gelb.gelb_ast import ASTNodes as A
from gelb.gelb_ast.CanonicalType import CanonicalType
from gelb.gelb_ast.SymbolDefinition import SymbolDefinition
from gelb.midware.c_family_lowering import prepare_c_family_ast
from gelb.midware.stencil import BlockStencil, StencilAccess, compute_opposite_mapping
from gelb.backends.stage3_backend_cpu_fortran_serial import FortranCodeGenerator
from gelb.backends.stage3_backend_cpu_highway import HighwayCodeGenerator
from gelb.backends.stage3_backend_gpu_cuda_cpp import CudaCppCodeGenerator


def program(constants='const int SIZE = 8;', *, extra='', initializer='f.out[x | :] = 1.0;',
            dynamic='f.out[x | :] = f.in[x | :];', geometry='nodes[:] = BULK;'):
    return f'''
    simulation_description("backend context");
    global_constants {{ {constants} }}
    lattices {{ lattice f(1, 3, real, 8, true); }}
    initializer Init {{ {initializer} }}
    dynamic Dyn {{ {dynamic} }}
    gauge Out -> (real val) {{ val = sum(f.in[x | :]); }}
    {extra}
    node_classes {{ node_class BULK(Init, Dyn, Out); node_class EMPTY() masked; }}
    geometry {{ {geometry} }}
    '''


def compile_context(source, prepared=False):
    result = compile_source(source, PipelineProfile.CODEGEN,
                            PipelineOptions(require_stencils=True, require_geometry=True))
    if prepared:
        result.ast = prepare_c_family_ast(result.ast)
    return build_backend_context(result)


@pytest.mark.parametrize('prepared', [False, True])
def test_exact_constants_and_width_conversion(prepared):
    context = compile_context(program('''
        const array[int, 2] HUGE = {18014399583223809, 9007199254740993};
        const array[int8, 2] BYTE = {255, 128};
        const array[real32, 2] ROUNDED = {16777217.0, -16777217.0};
        const array[real32, 2] OVER = {1.0e300, -1.0e300};
        const array[int16, {2, 2}] MATRIX = {{65535, 32768}, {2, 3}};
    '''), prepared)
    constants = context.global_constants
    huge = constants['HUGE']
    assert huge.dims == (2,)
    assert type(huge.elements[0].raw_value) is int
    assert huge.elements[0].raw_value == 18014399583223809
    assert huge.folded == (18014399583223809, 9007199254740993)
    assert constants['BYTE'].folded == (-1, -128)
    assert [e.converted_value for e in constants['ROUNDED'].elements] == [16777216.0, -16777216.0]
    assert [e.special_value for e in constants['OVER'].elements] == [float('inf'), -float('inf')]
    assert [e.converted_value for e in constants['OVER'].elements] == [float('inf'), -float('inf')]
    assert constants['OVER'].folded == (float('inf'), -float('inf'))
    assert constants['MATRIX'].matrix == ((-1, -32768), (2, 3))
    with pytest.raises(TypeError):
        constants['HUGE'] = huge
    with pytest.raises(FrozenInstanceError):
        huge.dtype = 'real'


@pytest.mark.parametrize('special', [float('inf'), -float('inf'), float('nan')])
def test_nonfinite_matrix_retains_folded_values(special):
    import math
    result = compile_source(program('const array[real32, {2, 2}] M = {{1.0, 2.0}, {3.0, 4.0}};'),
                            PipelineProfile.CODEGEN,
                            PipelineOptions(require_stencils=True, require_geometry=True))
    matrix = result.ast.global_constants.stmts[0].value
    while isinstance(matrix, A.TypePromotionNode_N):
        matrix = matrix.expr
    matrix.value[0].value[0].value = special
    context = build_backend_context(result)
    element = context.global_constants['M'].rows[0][0]
    assert not math.isfinite(element.converted_value)
    assert not math.isfinite(element.special_value)
    assert not math.isfinite(context.global_constants['M'].matrix[0][0])
    generator = FortranCodeGenerator(context.ast, backend_context=context)
    spelling = generator._fortran_constant_element(element, 'real32')
    assert spelling.startswith('ieee_value(')
    assert context.program_facts.uses_nonfinite


@pytest.mark.parametrize('dimensions', [1, 2, 3])
def test_shared_opposites(dimensions):
    axes = ['x', 'y', 'z'][:dimensions]
    names = ['EX', 'EY', 'EZ'][:dimensions]
    constants = ' '.join(f'const array[int, 3] {name} = {{0, 1, -1}};' for name in names)
    velocities = names[0] if dimensions == 1 else '{' + ', '.join(names) + '}'
    coords = ', '.join(axes)
    sizes = '8' if dimensions == 1 else '{' + ', '.join(['8'] * dimensions) + '}'
    periodic = 'true' if dimensions == 1 else '{' + ', '.join(['true'] * dimensions) + '}'
    source = f'''
    simulation_description("opposites");
    global_constants {{ {constants} }}
    lattices {{ lattice f({dimensions}, 3, real, {sizes}, {periodic}); }}
    initializer Init {{ f.out[{coords} | :] = 1.0; }}
    dynamic Dyn {{ f.out[{coords} | :] = bounce_back_dfs(f, {coords}, {velocities}); }}
    gauge Out -> (real val) {{ val = sum(f.in[{coords} | :]); }}
    node_classes {{ node_class BULK(Init, Dyn, Out); }}
    geometry {{ nodes[{', '.join([':'] * dimensions)}] = BULK; }}
    '''
    context = compile_context(source)
    assert context.opp_tables[tuple(names)] == (0, 2, 1)
    assert compute_opposite_mapping([[0, 1, -1]] * dimensions, 3) == [0, 2, 1]
    stencil = context.stencils.blocks['Dyn']
    assert stencil.offset_bounds(dimensions) == ((1, 1),) * dimensions
    assert context.stencils.offset_bounds('Dyn', dimensions, writes=True) == ((0, 0),) * dimensions
    with pytest.raises(ValueError, match='No opposite'):
        compute_opposite_mapping([[1]], 1)


def test_read_and_write_bounds_are_independent():
    stencil = BlockStencil('A', 'dynamic',
                           reads=[StencilAccess('f', (-2, 1), 0), StencilAccess('f', (3, -4), 1)],
                           writes=[StencilAccess('f', (1, -2), 0)])
    assert stencil.offset_bounds(2) == ((2, 3), (4, 1))
    assert stencil.offset_bounds(2, writes=True) == ((0, 1), (2, 0))
    assert BlockStencil('empty', 'gauge').offset_bounds(3) == ((0, 0),) * 3


def test_active_and_whole_program_facts_and_partial_outputs():
    context = compile_context(program(extra='''
        initializer Unused { f.out[x | :] = min(random(), real(t)); }
    ''', geometry='nodes[:] = EMPTY; nodes[1:6] = BULK;'))
    assert not context.program_facts.active_uses_random
    assert not context.program_facts.active_uses_real_minmax
    assert context.program_facts.uses_random
    assert context.program_facts.uses_implicit_t
    assert [decl.name.name for decl in context.gauge_outputs.outputs] == ['val']
    assert context.gauge_outputs.partial
    active = compile_context(program(initializer='f.out[x | :] = min(random(), 1.0);'))
    assert active.program_facts.active_uses_random
    assert active.program_facts.active_uses_real_minmax
    assert not active.gauge_outputs.partial
    assert not active.program_facts.uses_implicit_t


def test_facts_use_an_explicit_stack():
    random = A.IntrinsicFunctionCall_N(None, 'random', A.List_N(None))
    random.canonical_type = CanonicalType('real', ())
    node = random
    for _ in range(2500):
        node = A.Add_N(None, node, A.RealLiteral_N(None, 1.0))
    facts = ProgramFacts.collect(node, [node])
    assert facts.active_uses_random and facts.uses_random


@pytest.mark.parametrize('generator', [FortranCodeGenerator, HighwayCodeGenerator, CudaCppCodeGenerator])
def test_required_context_and_matching_ast(generator):
    with pytest.raises(ValueError, match='BackendContext is required'):
        generator(None)
    context = compile_context(program())
    with pytest.raises(ValueError, match='AST does not match'):
        generator(object(), backend_context=context)


def test_local_arrays_use_only_the_active_symbol_table():
    context = compile_context(program('const array[int, 2] PARENT = {1, 2};'), True)
    generator = HighwayCodeGenerator(context.ast, backend_context=context)
    parent = SymbolsTable()
    inherited = SymbolDefinition('PARENT', 'constant', None)
    inherited.canonical_type = CanonicalType('int', (2,))
    parent.append(inherited)
    local = SymbolsTable(parent)
    own = SymbolDefinition('tmp', 'variable', None)
    own.canonical_type = CanonicalType('real', (7,))
    local.append(own)
    generator._current_block = SimpleNamespace(symbol_defs=local)
    assert generator._local_array_type('PARENT') is None
    assert generator._array_size('PARENT') == 2
    assert generator._array_size('tmp') == 7
    previous = generator._current_block
    def fail(*args, **kwargs):
        assert generator._current_block is context.ast.initializers[0]
        raise RuntimeError('body')
    generator._emit_block_body_inner = fail
    with pytest.raises(RuntimeError, match='body'):
        generator._emit_block_body(context.ast.initializers[0], context='init')
    assert generator._current_block is previous


@pytest.mark.parametrize('generator', [FortranCodeGenerator, HighwayCodeGenerator, CudaCppCodeGenerator])
def test_emission_keeps_constant_nodes_unchanged(generator):
    context = compile_context(program('''
        const array[int8, 2] BYTES = {255, 128};
        const array[real32, 2] VALUES = {1.25, 2.75};
    '''), prepared=generator is not FortranCodeGenerator)
    elements = [e.node for entry in context.global_constants.values() for e in entry.elements]
    before = [(id(node), type(node), str(node), node.canonical_type) for node in elements]
    generator(context.ast, backend_context=context).generate()
    assert [(id(node), type(node), str(node), node.canonical_type) for node in elements] == before
    assert [id(e.node) for entry in context.global_constants.values() for e in entry.elements] == [row[0] for row in before]


def test_gauge_output_order_comes_from_active_node_classes():
    source = program(extra='gauge Other -> (real zz, real aa) { zz = 1.0; aa = 2.0; }',
                     geometry='nodes[:] = SECOND; nodes[1:6] = BULK;')
    source = source.replace('node_class EMPTY() masked;', 'node_class SECOND(Init, Dyn, Other);')
    context = compile_context(source)
    assert [decl.name.name for decl in context.gauge_outputs.outputs] == ['zz', 'aa', 'val']
    assert context.gauge_outputs.partial


@pytest.mark.parametrize('intrinsic', ['upstream_dfs', 'bounce_back_dfs'])
def test_promoted_velocity_entries(intrinsic):
    from gelb.compiler_pipeline import _walk_nodes
    source = program('const array[int,3] EX={0,1,-1};',
                     dynamic=f'array[real,3] u={intrinsic}(f,x,EX); f.out[x|:]=u;')
    result = compile_source(source, PipelineProfile.CODEGEN,
                            PipelineOptions(require_stencils=True, require_geometry=True))
    # The bounce validator rejects mixed-width source sets; exercise the context
    # handoff independently of that earlier validation.
    call = next(n for n in _walk_nodes((result.ast,))
                if isinstance(n, A.IntrinsicFunctionCall_N) and n.function_name == intrinsic)
    call.arguments.elements[-1] = A.TypePromotionNode_N(
        None, call.arguments[-1], A.ArrayDataType_N(None, 'int', A.IntLiteral_N(None, 3)))
    context = build_backend_context(result)
    text = FortranCodeGenerator(context.ast, backend_context=context).generate()
    assert 'g__e_x' in text
    if intrinsic == 'bounce_back_dfs':
        assert context.opp_tables[('EX',)] == (0, 2, 1)


def test_mixed_width_upstream_matches_uniform_emission():
    source = '''simulation_description("streaming widths");
    global_constants {
        const array[int8,5] EX={0,1,0,-1,0};
        const array[int,5] EY={0,0,1,0,-1};
    }
    lattices { lattice f(2,5,real,{4,4},{true,true}); }
    initializer I { f.out[x,y|:]={1.0,2.0,3.0,4.0,5.0}; }
    dynamic D { array[real,5] u=upstream_dfs(f,x,y,{EX,EY}); f.out[x,y|:]=u; }
    gauge G -> (real v) { v=f.in[x,y|1]; }
    node_classes { node_class B(I,D,G); }
    geometry { nodes[:,:]=B; }
    '''
    mixed = compile_context(source)
    uniform = compile_context(source.replace('int8,5', 'int,5'))
    def body(context):
        gen = FortranCodeGenerator(context.ast, backend_context=context)
        text = gen.generate()
        return text[text.index('! --- Dynamic:'):]
    assert body(mixed) == body(uniform)


@pytest.mark.parametrize('expression,random,minmax', [
    ('random()', True, False),
    ('real(min(f.in[x|0], f.in[x|1]))', False, True),
    ('real(max(f.in[x|0], f.in[x|1]))', False, True),
])
def test_gauge_only_program_facts(expression, random, minmax):
    source = program().replace('lattice f(1, 3, real,', 'lattice f(1, 3, real32,')
    source = source.replace('val = sum(f.in[x | :]);', f'val = {expression};')
    context = compile_context(source)
    assert context.program_facts.active_uses_random is random
    assert context.program_facts.active_uses_real_minmax is minmax
    generator = FortranCodeGenerator(context.ast, backend_context=context)
    assert generator._uses_random is random
    assert generator._uses_real_minmax is minmax


def test_distinct_velocity_sets_have_distinct_opposites():
    context = compile_context(program('''
        const array[int,3] EX={0,1,-1}; const array[int,3] FX={1,0,-1};
    ''', dynamic='''
        array[real,3] u=bounce_back_dfs(f,x,EX);
        array[real,3] v=bounce_back_dfs(f,x,FX);
        f.out[x|:]=u+v;
    '''))
    assert dict(context.opp_tables) == {('EX',): (0,2,1), ('FX',): (2,1,0)}


@pytest.mark.parametrize('value', ['EX0', '-EX0', '{0,1,-1}'])
def test_identifier_mapping_before_constant_array_folding(value):
    from gelb.tests.test_utils import get_typed_ast
    from gelb.utils.identifier_mapping import collect_identifier_mapping
    source = program(f'const array[int,3] EX0={{0,-1,1}}; const array[int,3] EX={value};',
                     dynamic='array[real,3] u=bounce_back_dfs(f,x,EX); f.out[x|:]=u;')
    ast = get_typed_ast(source)
    sections = collect_identifier_mapping(ast)
    dynamic = next(s for s in sections if s['title'] == 'Dynamic Dyn')
    assert dynamic['entries'] == [('u', 'gelb_b1_g_u')]


def test_unevaluable_constant_keeps_fold_fallback():
    result = compile_source(program('const array[real32,{2,2}] M={{1.0,2.0},{3.0,4.0}};'),
                            PipelineProfile.CODEGEN,
                            PipelineOptions(require_stencils=True, require_geometry=True))
    node = result.ast.global_constants.stmts[0].value
    while isinstance(node, A.TypePromotionNode_N):
        node = node.expr
    node.value[0].value.elements[0] = A.Mul_N(None, A.RealLiteral_N(None, 1.0e300),
                                            A.RealLiteral_N(None, 1.0e300))
    context = build_backend_context(result)
    assert context.global_constants['M'].rows[0][0].raw_value is None
    assert context.global_constants['M'].matrix is None


def test_identifier_mapping_matches_multiple_node_class_declarations():
    from gelb.utils.identifier_mapping import collect_identifier_mapping

    source = '''simulation_description("mapping across node classes");
    lattices { lattice f(1, 1, real, 8, true); }
    initializer LeftInit { real left_start = real(x); f.out[x|0] = left_start; }
    dynamic LeftStep { real left_next = f.in[x|0]; f.out[x|0] = left_next; }
    gauge LeftGauge -> (real left_value) { left_value = f.in[x|0]; }
    initializer RightInit { real right_start = real(x); f.out[x|0] = right_start; }
    dynamic RightStep { real right_next = f.in[x|0]; f.out[x|0] = right_next; }
    gauge RightGauge -> (real right_value) { right_value = f.in[x|0]; }
    node_classes {
        node_class LEFT(LeftInit, LeftStep, LeftGauge);
        node_class RIGHT(RightInit, RightStep, RightGauge);
    }
    geometry { nodes[:] = LEFT; nodes[2:5] = RIGHT; }
    '''
    context = compile_context(source)
    code = FortranCodeGenerator(context.ast, backend_context=context).generate()
    declarations = {line.split('::', 1)[1].strip() for line in code.splitlines()
                    if line.strip().startswith('double precision :: ')}
    mappings = {section['title']: dict(section['entries'])
                for section in collect_identifier_mapping(context.ast)}
    expected = {
        'Initializer LeftInit': 'left_start',
        'Dynamic LeftStep': 'left_next',
        'Gauge LeftGauge': 'left_value',
        'Initializer RightInit': 'right_start',
        'Dynamic RightStep': 'right_next',
        'Gauge RightGauge': 'right_value',
    }
    names = [mappings[section][original] for section, original in expected.items()]
    assert len(set(names)) == 6
    assert set(names) <= declarations
