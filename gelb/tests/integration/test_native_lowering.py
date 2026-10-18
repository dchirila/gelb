"""Native-lowering regressions compiled and run through the normal gelb-run defaults."""

import sys

import numpy as np
import pytest

from gelb.tests.integration.test_tutorial_regressions import (
    BACKENDS, netCDF4, run_source,
)


@pytest.fixture(autouse=True)
def runner_defaults(monkeypatch):
    for key in ('GELB_FFLAGS', 'GELB_CXXFLAGS', 'GELB_NVCC_FLAGS', 'GELBC_EXTRA'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('OMP_NUM_THREADS', '1')


def program(gauge='v = u.in[x | 0];', *, description='native diagnostic check',
            outputs='real v', globals='', initializer='u.out[x | 0] = 1.0;',
            dynamic='u.out[x | 0] = u.in[x | 0];', size=4):
    return f'''simulation_description("{description}");
{globals}
lattices {{ lattice u(1,1,real,{size},false); }}
initializer I {{ {initializer} }}
dynamic D {{ {dynamic} }}
gauge G -> ({outputs}) {{ {gauge} }}
node_classes {{ node_class BULK(I,D,G); }}
geometry {{ nodes[:] = BULK; }}
'''


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('description', [
    'first line\nsecond line', "a user's test", 'café λ\tC:\\new\\test',
])
def test_description_escaping(tmp_path, backend, description):
    data = run_source(tmp_path, backend, program(description=description))
    np.testing.assert_array_equal(data['v'], np.ones((2, 4)))
    with netCDF4.Dataset(next(tmp_path.glob('*.nc'))) as nc:
        assert nc.description == description


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('operator', ['==', '!='])
def test_boolean_comparison(tmp_path, backend, operator):
    data = run_source(tmp_path, backend, program(
        f'bool a = x > 0; bool b = x > 1; v = int(a {operator} b);'))
    expected = [1, 0, 1, 1] if operator == '==' else [0, 1, 0, 0]
    np.testing.assert_array_equal(data['v'], [expected, expected])


@pytest.mark.parametrize('backend', BACKENDS)
def test_boolean_array_comparison(tmp_path, backend):
    data = run_source(tmp_path, backend, program('''
        array[bool,2] a = {x > 0, x > 1};
        array[bool,2] b = {x > 1, x > 0};
        array[bool,2] c = a == b;
        v = int(c[0]) + int(c[1]);'''))
    np.testing.assert_array_equal(data['v'], [[2, 0, 2, 2]] * 2)


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('gauge,expected', [
    ('array[int,2] a = {x,1}; v = sum(a);', [1, 2, 3, 4]),
    ('bool b = x > 0; array[bool,2] a = {b,true}; v = int(a[0]);', [0, 1, 1, 1]),
    ('array[int,2] a = {x,2147483648}; v = sum(a);',
     [2147483648, 2147483649, 2147483650, 2147483651]),
    ('array[real32,2] a = {real32(x),real32(1.5)}; v = sum(a);', [1.5, 2.5, 3.5, 4.5]),
])
def test_array_constructor_kinds(tmp_path, backend, gauge, expected):
    data = run_source(tmp_path, backend, program(gauge))
    np.testing.assert_array_equal(data['v'], [expected, expected])


@pytest.mark.parametrize('backend', BACKENDS[:1])
def test_matrix_constructor_kinds(tmp_path, backend):
    # A matrix literal in a block is a separate construct the C++
    # backends do not lower (Highway and CUDA stop on the 2-D array
    # literal inside gelbc); exercise the Fortran constructor here.
    data = run_source(tmp_path, backend, program('''
        array[int,{2,2}] a = {{x,1},{2,3}};
        v = a[0,0] + a[0,1] + a[1,0] + a[1,1];'''))
    np.testing.assert_array_equal(data['v'], [[6, 7, 8, 9]] * 2)


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('partial', [False, True])
def test_boolean_gauge(tmp_path, backend, partial):
    source = program('v = x > 0;', outputs='bool v', size=17)
    if partial:
        source = source.replace('node_class BULK(I,D,G);',
                                'node_class BULK(I,D,G); node_class MASK(I,D) masked;')
        source = source.replace('nodes[:] = BULK;', 'nodes[:] = BULK; nodes[8] = MASK;')
    data = run_source(tmp_path, backend, source)
    expected = np.ones(17, dtype=np.int8)
    expected[0] = 0
    if partial:
        expected[8] = 0
    np.testing.assert_array_equal(data['v'], [expected, expected])
    with netCDF4.Dataset(next(tmp_path.glob('*.nc'))) as nc:
        assert nc['v'].dtype == np.dtype('int8')


@pytest.mark.parametrize('backend', BACKENDS)
def test_case_distinct_gauge_names(tmp_path, backend):
    data = run_source(tmp_path, backend, program(
        'a = x; A = x+1; a_A = x+2; a_a = x+3;',
        outputs='real a, real A, real a_A, real a_a'))
    for i, name in enumerate(['a', 'A', 'a_A', 'a_a']):
        np.testing.assert_array_equal(data[name], [np.arange(4) + i] * 2)


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('name', ['A' * 32, 'a' * 64])
def test_long_identifiers(tmp_path, backend, name):
    # Also exercise derived buffer IDs, lattice buffer selectors and halo
    # procedure names; long names sharing a prefix must remain distinct.
    lattice = name + 'lattice'
    output = name + 'output'
    source = program(f'real {name} = x; real {name}b = x+1; '
                     f'{output} = {name} + {name}b + u.in[x | 0];',
                     outputs=f'real {output}')
    source = source.replace('lattice u(', f'lattice {lattice}(')
    source = source.replace('u.in[', f'{lattice}.in[').replace('u.out[', f'{lattice}.out[')
    source = source.replace(',false);', ',true);')
    data = run_source(tmp_path, backend, source)
    np.testing.assert_array_equal(data[output], [[2, 4, 6, 8]] * 2)


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('initializer,dynamic', [
    ('real a = 1.0; u.out[x | 0] = a;',
     'array[real,2] a = {u.in[x | 0],2.0}; u.out[x | 0] = a[0];'),
    ('array[real,3] a = {1.0,2.0,3.0}; u.out[x | 0] = a[0];',
     'array[real,2] a = {u.in[x | 0],2.0}; u.out[x | 0] = a[0];'),
    ('bool a = x >= 0; u.out[x | 0] = real(a);',
     'real a = u.in[x | 0]; u.out[x | 0] = a;'),
])
def test_block_local_identity(tmp_path, backend, initializer, dynamic):
    data = run_source(tmp_path, backend, program(initializer=initializer, dynamic=dynamic))
    np.testing.assert_array_equal(data['v'], np.ones((2, 4)))


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('gauge,globals,expected', [
    ('real u = x; v = u;', '', [0, 1, 2, 3]),
    ('array[real,2] a = {real(x),2.0}; v = a[0];',
     'global_constants { const real a = 9.0; }', [0, 1, 2, 3]),
])
def test_local_shadowing(tmp_path, backend, gauge, globals, expected):
    data = run_source(tmp_path, backend, program(gauge, globals=globals))
    np.testing.assert_array_equal(data['v'], [expected, expected])


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('kind', ['real', 'real32'])
@pytest.mark.parametrize('special', ['nan', 'inf', '-inf'])
def test_nonfinite_literal_contract(tmp_path, monkeypatch, backend, kind, special):
    # Supply post-fold literals at the backend boundary: the frontend
    # rejects non-finite source literals and CLI overrides, so only the
    # IEEE folder produces them.
    # The shim changes only a finite sentinel after the normal frontend
    # and midware passes; gelb-run still builds/runs with its default flags.
    launcher = tmp_path / 'literal-python'
    launcher.write_text(f'#!{sys.executable}\n' + r"""
import functools
import importlib
import os
import runpy
import sys
from gelb.gelb_ast.ASTNodes import Node_N, RealLiteral_N

def inject(original, ast, *args, **kwargs):
    seen = set()
    def visit(node):
        if isinstance(node, Node_N):
            if id(node) in seen:
                return
            seen.add(id(node))
            if isinstance(node, RealLiteral_N) and node.value == 12345.0:
                node.value = float(os.environ['GELB_TEST_IEEE_VALUE'])
            for child in vars(node).values():
                visit(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                visit(child)
    visit(ast)
    return original(ast, *args, **kwargs)

for suffix, entry in [('cpu_fortran_serial', 'generate_fortran'),
                      ('cpu_highway', 'generate_cpu_highway'),
                      ('gpu_cuda_cpp', 'generate_cuda_cpp')]:
    module = importlib.import_module('gelb.backends.stage3_backend_' + suffix)
    setattr(module, entry, functools.partial(inject, getattr(module, entry)))
assert sys.argv[1] == '-m'
module = sys.argv[2]
sys.argv = sys.argv[2:]
runpy.run_module(module, run_name='__main__')
""")
    launcher.chmod(0o755)
    monkeypatch.setenv('GELB_TEST_IEEE_VALUE', special)
    source = program('''
        KIND local = SPECIAL;
        array[KIND,2] vector = {1.0,1.0};
        array[KIND,2] product = matmul(MATRIX,vector);
        v = local; a = VALUES[0]; b = product[1];'''.replace('KIND', kind),
        outputs='real v, real a, real b', globals='''global_constants {
            const KIND SPECIAL = 12345.0;
            const array[KIND,2] VALUES = {SPECIAL,1.0};
            const array[KIND,{2,2}] MATRIX = {{1.0,1.0},{SPECIAL,1.0}};
        }'''.replace('KIND', kind))
    data = run_source(tmp_path, backend, source, python=str(launcher))
    for name in ['v', 'a', 'b']:
        np.testing.assert_array_equal(data[name], np.full((2, 4), float(special)))


@pytest.mark.parametrize('backend', BACKENDS)
@pytest.mark.parametrize('name', ['u_storage', 'u_old', 'u_new', 'u_storage_t', 'u_buf_t', 'g0_1_u_storage'])
def test_global_internal_name_collision(tmp_path, backend, name):
    source = program(f'v = u.in[x | 0] + {name};',
                     globals=f'global_constants {{ const real {name} = 2.0; }}')
    data = run_source(tmp_path, backend, source)
    np.testing.assert_array_equal(data['v'], np.full((2, 4), 3.0))


@pytest.mark.parametrize('backend', BACKENDS)
def test_local_internal_name_collision(tmp_path, backend):
    # Enough cells for Highway's SIMD path as well as scalar heads/tails.
    source = program('real u_storage = x; v = u.in[x | 0] + u_storage;', size=17)
    data = run_source(tmp_path, backend, source)
    np.testing.assert_array_equal(data['v'], [np.arange(17) + 1] * 2)


@pytest.mark.parametrize('backend', BACKENDS[1:])
@pytest.mark.parametrize('variant', ['plain', 'alternate', 'optimized'])
def test_internal_names_in_storage_paths(tmp_path, monkeypatch, backend, variant):
    if backend == 'cpu_highway':
        layout = {'plain': 'soa', 'alternate': 'aos', 'optimized': 'cbt'}[variant]
        if layout == 'cbt':
            from gelb.backends.highway.common import _detect_avx512_available
            if not _detect_avx512_available():
                pytest.skip('CBT requires AVX-512')
        extra = f'--storage-layout {layout}'
    else:
        extra = {'plain': '--cuda-ldg --cuda-stwt',
                 'alternate': '--cuda-tiled',
                 'optimized': '--cuda-tiled --cuda-ldg --cuda-stwt'}[variant]
    monkeypatch.setenv('GELBC_EXTRA', extra)
    source = '''simulation_description("internal names in periodic storage");
lattices { lattice u(2,1,real,{32,8},{true,true}); }
initializer I { u.out[x,y | 0] = real(x+10*y); }
dynamic D { u.out[x,y | 0] = u.in[x-1,y | 0]; }
gauge G -> (real v) { real u_storage = 1.0; v = u.in[x,y | 0] + u_storage; }
node_classes { node_class BULK(I,D,G); }
geometry { nodes[:,:] = BULK; }
'''
    data = run_source(tmp_path, backend, source)
    initial = np.arange(32)[None, :] + 10*np.arange(8)[:, None]
    np.testing.assert_array_equal(data['v'][0], initial + 1)
    np.testing.assert_array_equal(data['v'][1], np.roll(initial, 1, axis=1) + 1)


@pytest.mark.parametrize('backend', BACKENDS[:1])
def test_identifier_mapping_matches_scoped_emission(tmp_path, backend):
    from gelb.tests.test_utils import get_typed_ast
    from gelb.utils.identifier_mapping import collect_identifier_mapping
    from gelb.backends.stage3_backend_cpu_fortran_serial import generate_fortran

    source = program('real a = u.in[x | 0]; v = a;',
                     initializer='real a = 1.0; u.out[x | 0] = a;',
                     dynamic='bool a = x >= 0; u.out[x | 0] = real(a);')
    ast = get_typed_ast(source)
    code = generate_fortran(ast)
    names = [native for section in collect_identifier_mapping(ast)
             for original, native in section['entries'] if original == 'a']
    assert len(names) == len(set(names)) == 3
    assert all(name in code for name in names)
    data = run_source(tmp_path, backend, source)
    np.testing.assert_array_equal(data['v'], np.ones((2, 4)))
