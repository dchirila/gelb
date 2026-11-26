"""``dot_prod`` of a constant ``real`` array with a per-cell ``real32`` array
is written in the result's type on the C++ and CUDA paths.

The result is ``real`` and each element converts before it is multiplied
(user manual, Numerical semantics: Types and promotion).  The helpers that
take their type from the array they read would add in binary32, so this one
case names the result's type (``gelb_dot_prod_const_as<double>``,
``gelb_signed_sum_as<double>``) or converts each element of the written-out
chain.  Operands of one width keep the deducing helpers and the bare chain.
"""

import functools
import re

import pytest

from gelb.backends.stage3_backend_cpu_highway import HighwayCodeGenerator
from gelb.backends.stage3_backend_gpu_cuda_cpp import generate_cuda_cpp
from gelb.compiler_pipeline import (
    PipelineOptions, PipelineProfile, build_backend_context, compile_source,
    prepare_c_family_ast,
)

CONFIGS = ('soa', 'aos', 'cbt', 'cuda')
NUMBERED = re.compile(r'\b(gelb_dp_(?:coeff|idx|pos|neg)|g__gelb_dpa|g___[A-Za-z]+)_\d+')
CONSTANTS = '''
    const int Q = 3;
    const array[real, 3] WG = {0.1, 0.7, 1.3};
    const array[real, 3] WZ = {0.5, 0.0, 0.25};
    const array[real, 3] WS = {1.0, -1.0, 1.0};
    const array[real, 3] WP = {1.0, 1.0, 1.0};
    const array[real, 3] WN = {-1.0, -1.0, -1.0};
    const array[real32, 3] WG32 = {0.1, 0.7, 1.3};
    const array[real32, 3] WS32 = {1.0, -1.0, 1.0};
    const array[real32, 3] WP32 = {1.0, 1.0, 1.0};
    const array[int, 3] KG = {1, 2, 3};
    const array[int, 3] KS = {1, -1, 1};
    const array[int, 3] KP = {1, 1, 1};
    const array[int, 3] EX = {0, 1, -1};
'''
SIZES = {1: ('64', 'true'), 2: ('{64, 4}', '{true, true}'), 3: ('{64, 4, 4}', '{true, true, true}')}
COORDS = {1: 'x', 2: 'x, y', 3: 'x, y, z'}


def program(gauge, *, dims=1, q=3, init='', dynamic='', functions=''):
    """``g`` is a real32 lattice, ``h`` a real one; ``C`` in a block is the
    cell's coordinates."""
    size, periodic = SIZES[dims]
    source = f'''
    simulation_description("mixed-width dot_prod");
    global_constants {{ {CONSTANTS} }}
    {functions}
    lattices {{ lattice g({dims}, {q}, real32, {size}, {periodic});
               lattice h({dims}, {q}, real, {size}, {periodic}); }}
    initializer I {{ g.out[C | :] = 1.0 + real(x); h.out[C | :] = 1.0 + real(x); {init} }}
    dynamic D {{ g.out[C | :] = g.in[C | :]; {dynamic} }}
    gauge G -> (real v) {{ {gauge} }}
    node_classes {{ node_class B(I, D, G); }}
    geometry {{ nodes[{', '.join(':' * dims)}] = B; }}
    '''
    if 'h.out[C' not in dynamic:
        source = source.replace('dynamic D {', 'dynamic D { h.out[C | :] = h.in[C | :];')
    return source.replace('[C', '[' + COORDS[dims])


@functools.lru_cache(maxsize=None)
def emitted(source, config):
    result = compile_source(source, PipelineProfile.CODEGEN,
                            PipelineOptions(require_stencils=True, require_geometry=True))
    result.ast = prepare_c_family_ast(result.ast)
    context = build_backend_context(result)
    if config == 'cuda':
        return generate_cuda_cpp(result.ast, backend_context=context)
    return HighwayCodeGenerator(result.ast, backend_context=context,
                                storage_layout=config).generate()


def written(code, name):
    """Every right-hand side the generated source gives the local ``name``,
    with the numbers of the hoisted names removed.  The ``0`` that a
    function's result is declared with is not one of them."""
    found = set(re.findall(rf'^[ \t]*(?:[A-Za-z_][\w:<>]* )?g_{name} = (.+);$', code, re.M)) - {'0'}
    assert found, name
    return {NUMBERED.sub(r'\1', rhs) for rhs in found}


def chain(array, sign='+', cast='static_cast<double>({})'):
    terms = [cast.format(f'{array}[{i}]') for i in range(3)]
    return '(' + ('-' if sign == '-' else '') + f' {sign} '.join(terms) + ')'


# What a mixed call is written as, for the per-cell array ``array``.
MIXED = {
    'general': ('WG', 'gelb::gelb_dot_prod_const_as<double>(gelb_dp_coeff, {0}, gelb_dp_idx)'.format),
    'zero_coefficient': ('WZ', 'gelb::gelb_dot_prod_const_as<double>(gelb_dp_coeff, {0}, gelb_dp_idx)'.format),
    'plus_and_minus_one': ('WS', 'gelb::gelb_signed_sum_as<double>({0}, gelb_dp_pos, gelb_dp_neg)'.format),
    'all_plus_one': ('WP', chain),
    'all_minus_one': ('WN', lambda array: chain(array, '-')),
}
ORDERS = {'constant_first': 'dot_prod({0}, {1})'.format, 'array_first': 'dot_prod({1}, {0})'.format}


def calls(array, forms=MIXED, prefix=''):
    """One local per form and argument order, named ``<prefix><order>_<form>``."""
    return ' '.join(f'real {prefix}{order}_{form} = {call(constant, array)};'
                    for form, (constant, _) in forms.items() for order, call in ORDERS.items())


def total(forms=MIXED, prefix=''):
    return ' + '.join(f'{prefix}{order}_{form}' for form in forms for order in ORDERS)


LOCAL = program(f'array[real32, 3] a = g.in[x | :]; {calls("a")} v = {total()};')


@pytest.mark.parametrize('config', CONFIGS)
@pytest.mark.parametrize('order', ORDERS)
@pytest.mark.parametrize('form', MIXED)
def test_mixed_call_is_written_in_the_result_type(form, order, config):
    """Each of the three ways a constant-coefficient ``dot_prod`` is written
    carries the result's type when the per-cell array is narrower, in either
    argument order: the general helper (a zero coefficient included), the
    +1/-1 helper, and the chain of an all +1 or all -1 constant."""
    code = emitted(LOCAL, config)
    assert written(code, f'{order}_{form}') == {MIXED[form][1]('g_a')}


@pytest.mark.parametrize('config', CONFIGS)
def test_mixed_call_keeps_binary64_coefficients_and_every_term(config):
    """The coefficients of a mixed call are the constant's binary64 values,
    a zero among them (user manual, Numerical semantics: Reproducibility:
    every term counts)."""
    code = emitted(LOCAL, config)
    for values in ('{ 0.1, 0.7, 1.3 }', '{ 0.5, 0.0, 0.25 }'):
        assert re.search(rf'constexpr double gelb_dp_coeff_\d+\[\] = {re.escape(values)};', code)
    assert 'float gelb_dp_coeff' not in code
    assert 'float g_a[3];' in code


OPERANDS = {
    'whole_slice': ('g.in[x | :]', 3, 'g__gelb_dpa'),
    'partial_slice': ('g.in[x | 1:3]', 5, 'g__gelb_dpa'),
    'neighbour_slice': ('g.in[x - 1 | :]', 3, 'g__gelb_dpa'),
    'named_extent': ('aq', 3, 'g_aq'),
}


@pytest.mark.parametrize('config', CONFIGS)
@pytest.mark.parametrize('operand', OPERANDS)
def test_mixed_call_on_a_lattice_slice_or_a_named_extent(operand, config):
    """A ``real32`` lattice slice passed directly (whole, partial or a
    neighbour's) is hoisted into a ``real32`` local, and an array declared
    with a named extent is one too: all three ways of writing the call
    widen them, in either argument order."""
    argument, q, array = OPERANDS[operand]
    code = emitted(program(f'array[real32, Q] aq = g.in[x | {"1:3" if q == 5 else ":"}]; '
                           f'{calls(argument)} v = {total()};', q=q), config)
    for form, (_, expected) in MIXED.items():
        for order in ORDERS:
            assert written(code, f'{order}_{form}') == {expected(array)}
    assert re.search(rf'float {array}(_\d+)?\[3\];', code)


FUNCTIONS = '''
    function General(array[real32, 3] u) -> (real r) { r = dot_prod(WG, u); }
    function Signed(array[real32, 3] u) -> (real r) { r = dot_prod(u, WS); }
    function Minus(array[real32, 3] u) -> (real r) { r = dot_prod(WN, u); }
'''
LITERAL = '{real32(1.5 + real(x)), real32(0.25), real32(2.0)}'


@pytest.mark.parametrize('config', CONFIGS)
@pytest.mark.parametrize('dims', [1, 2, 3])
def test_mixed_call_in_every_block_kind_and_dimension(dims, config):
    """The same three forms in an initializer, a dynamic block and a gauge
    of a 1-D, 2-D and 3-D program, and inside a user function, which is
    inlined where it is called."""
    source = program(
        f'array[real32, 3] a = g.in[C | :]; {calls("a", prefix="g_")} '
        f'v = {total(prefix="g_")} + General(a) + Signed(a) + Minus(a);',
        dims=dims, functions=FUNCTIONS,
        init=f'array[real32, 3] a = {LITERAL}; {calls("a", prefix="i_")} '
             f'h.out[C | 0] = {total(prefix="i_")};',
        dynamic=f'array[real32, 3] a = g.in[C | :]; {calls("a", prefix="d_")} '
                f'h.out[C | 0] = {total(prefix="d_")}; h.out[C | 1:2] = h.in[C | 1:2];')
    code = emitted(source, config)
    for prefix in ('i_', 'd_', 'g_'):
        for form, (_, expected) in MIXED.items():
            for order in ORDERS:
                assert written(code, f'{prefix}{order}_{form}') == {expected('g_a')}
    assert written(code, '__General_0_r') == {MIXED['general'][1]('g_a')}
    assert written(code, '__Signed_1_r') == {MIXED['plus_and_minus_one'][1]('g_a')}
    assert written(code, '__Minus_2_r') == {chain('g_a', '-')}


PLAIN = {
    'general': 'gelb::gelb_dot_prod_const(gelb_dp_coeff, {0}, gelb_dp_idx)'.format,
    'plus_and_minus_one': 'gelb::gelb_signed_sum({0}, gelb_dp_pos, gelb_dp_neg)'.format,
    'all_plus_one': lambda array: chain(array, cast='{}'),
    'all_minus_one': lambda array: chain(array, '-', cast='{}'),
}
# name: (the result's type, the constants of the four forms, the per-cell array)
UNIFORM = {
    'real_constant_real_array': ('real', ('WG', 'WS', 'WP', 'WN'), 'b'),
    'real32_constant_real32_array': ('real32', ('WG32', 'WS32', 'WP32', None), 'a'),
    'int_constant_real32_array': ('real32', ('KG', 'KS', 'KP', None), 'a'),
    'real32_constant_real_array': ('real', ('WG32', 'WS32', 'WP32', None), 'b'),
    'real_constant_streamed_real32_lattice': ('real', ('WG', 'WS', 'WP', 'WN'), 'upstream_dfs(g, x, EX)'),
}


def uniform_calls():
    out = []
    for name, (kind, constants, array) in UNIFORM.items():
        for form, constant in zip(PLAIN, constants):
            if constant is not None:
                out += [f'{kind} {name}_{order}_{form} = {call(constant, array)};'
                        for order, call in ORDERS.items()]
    return ' '.join(out)


CONTROLS = program(
    'array[real32, 3] a = g.in[x | :]; array[real, 3] b = h.in[x | :]; '
    'array[int, 3] n = int(h.in[x | :]); '
    f'{uniform_calls()} '
    'real real_constant_int_array = dot_prod(WG, n); '
    'real int_array_real_constant = dot_prod(n, WG); '
    'real real_array_real32_array = dot_prod(b, a); '
    'real real32_array_real_array = dot_prod(a, b); '
    'v = real_constant_int_array + int_array_real_constant + real_array_real32_array'
    ' + real32_array_real_array;')


@pytest.mark.parametrize('config', CONFIGS)
@pytest.mark.parametrize('pair', UNIFORM)
def test_operands_of_one_width_keep_the_deducing_helpers(pair, config):
    """Where the per-cell array already has the result's type, the call is
    written as before, with no type named and no conversion: two ``real``
    or two ``real32`` operands, an integer constant with a ``real32`` array
    (a ``real32`` result), a ``real32`` constant with a ``real`` array, and
    ``upstream_dfs`` of a ``real32`` lattice, whose value is an
    ``array[real, q]``."""
    code = emitted(CONTROLS, config)
    _, constants, array = UNIFORM[pair]
    name = 'g__gelb_dpa' if '(' in array else f'g_{array}'
    for form, constant in zip(PLAIN, constants):
        for order in ORDERS:
            if constant is not None:
                assert written(code, f'{pair}_{order}_{form}') == {PLAIN[form](name)}


@pytest.mark.parametrize('config', CONFIGS)
def test_a_program_without_a_mixed_call_names_no_real_type(config):
    """The typed helpers appear for the mixed case alone; a constant
    ``real`` array with an integer array stays the written-out sum that
    fuses nothing, and two per-cell arrays stay the bare chain."""
    code = emitted(CONTROLS, config)
    assert '_as<double>' not in code and '_as<float>' not in code
    products = ' + '.join(f'{c} * static_cast<double>(g_n[{i}])' for i, c in enumerate(('0.1', '0.7', '1.3')))
    assert written(code, 'real_constant_int_array') == {f'({products})'}
    assert written(code, 'int_array_real_constant') == {f'({products})'}
    assert written(code, 'real_array_real32_array') == {
        '(g_b[0] * g_a[0] + g_b[1] * g_a[1] + g_b[2] * g_a[2])'}
    assert written(code, 'real32_array_real_array') == {
        '(g_a[0] * g_b[0] + g_a[1] * g_b[1] + g_a[2] * g_b[2])'}


@pytest.mark.parametrize('layout', ['soa', 'cbt'])
def test_a_vector_body_keeps_its_descriptor_argument(layout):
    """In a program of ``real`` lattices alone a block is a vector body on
    SoA and CBT, and its helpers take the descriptor as before."""
    source = program('array[real, 3] b = h.in[x | :]; real general = dot_prod(WG, b); '
                     'real signed = dot_prod(b, WS); v = general + signed;')
    code = emitted(source.replace('real32', 'real'), layout)
    assert written(code, 'general') >= {'gelb::gelb_dot_prod_const(d, gelb_dp_coeff, g_b, gelb_dp_idx)'}
    assert written(code, 'signed') >= {'gelb::gelb_signed_sum(d, g_b, gelb_dp_pos, gelb_dp_neg)'}
    for name in ('general', 'signed'):
        assert not any('_as<' in rhs for rhs in written(code, name))
