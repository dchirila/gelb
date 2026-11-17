"""Static initialization copies every lattice without repeating its body."""

import re

from click.testing import CliRunner
import pytest

from gelb.backends.highway import common
from gelb.gelbc import cli


CONFIGS = [
    ('cpu_fortran_serial', '.f90', None),
    ('cpu_highway', '.cpp', 'soa'),
    ('cpu_highway', '.cpp', 'aos'),
    ('cpu_highway', '.cpp', 'cbt'),
    ('gpu_cuda_cpp', '.cu', None),
]


def emit(tmp_path, source, backend, suffix, layout):
    path, out = tmp_path / 'copy.gelb', tmp_path / ('copy' + suffix)
    path.write_text(source)
    args = [str(path), '-b', backend, '-o', str(out), '--nc-output', 'out.nc']
    if layout:
        args += ['--storage-layout', layout]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    return out.read_text()


@pytest.mark.parametrize('backend,suffix,layout', CONFIGS)
@pytest.mark.parametrize('masked', [False, True])
@pytest.mark.parametrize('sparse', [False, True])
def test_static_copy_covers_all_lattices_and_class_membership(
        tmp_path, monkeypatch, backend, suffix, layout, masked, sparse):
    if layout == 'cbt':
        # This test inspects source without compiling or running CBT code.
        monkeypatch.setattr(common._detect_avx512_available, '_cached', None, raising=False)
        monkeypatch.setenv('GELB_HAS_AVX512', '1')
    static = 'S(InitRand) masked' if masked else 'S(InitRand, G)'
    paint = 'nodes[where Odd(x)] = S;' if sparse else 'nodes[0:15] = S;'
    source = f"""
simulation_description("static buffers");
lattices {{ lattice f(1, 2, real, 33, false); lattice h(1, 3, real32, 33, false); }}
function Odd(int px) -> (bool result) {{ result = mod(px, 2) == 1; }}
initializer InitRand {{ f.out[x | :] = random(); h.out[x | :] = real32(random()); }}
initializer InitZero {{ f.out[x | :] = 0.0; h.out[x | :] = real32(0.0); }}
dynamic Copy {{ f.out[x | :] = f.in[x | :]; h.out[x | :] = h.in[x | :]; }}
gauge G -> (real value) {{ value = f.in[x | 0]; }}
node_classes {{ node_class {static}; node_class B(InitZero, Copy, G); }}
geometry {{ nodes[:] = B; {paint} }}
"""
    text = emit(tmp_path, source, backend, suffix, layout)
    assert not any(token in text for token in
                   ('initializer_copy', 'initializer_2nd_buffer', 'init2nd'))
    if suffix == '.f90':
        copy = text.split('! ========== Init (2nd buffer):', 1)[1].split(
            '! ========== Gauge at t=0', 1)[0]
        for name in ('g_f', 'g_h'):
            assert re.search(rf'\b{name}\(:, (.+), {name}_new\) = {name}\(:, \1, {name}_old\)', copy)
    elif suffix == '.cpp':
        copy = text.split('// Init (2nd buffer):', 1)[1].split(
            '// ========== Gauge at t=0', 1)[0]
        assert '-- SIMD' not in copy
    else:
        copy = text.split('__global__ void gelb_static_buffer_copy()', 1)[1].split(
            '\n}', 1)[0]
        if sparse:
            assert 'gelb_nc_map' in copy
        else:
            assert 'g_x >= 0 && g_x <= 15' in copy
        assert text.count('gelb_static_buffer_copy<<<') == 1
        assert text.index('gelb_static_buffer_copy<<<') > text.rindex('gelb_k_init_')
        assert 'gelb_static_buffer_copy<<<gelb_grid, gelb_block>>>();\n' in text
    if suffix != '.f90':
        for name in ('g0_1_f', 'g0_1_h'):
            assert re.search(rf'{name}_storage\[{name}_new\](.+) = {name}_storage\[{name}_old\]\1;', copy)
        assert 'gelb_df < 2' in copy and 'gelb_df < 3' in copy
    assert 'gelb_random' not in copy and 'random_number' not in copy


def test_cuda_static_copy_checks_each_grid_axis_and_dense_class_bound(tmp_path):
    source = """
simulation_description("two dimensional static copy bounds");
lattices { lattice f(2, 1, real, {17, 23}, {false, false}); }
initializer I { f.out[x, y | 0] = 1.0; }
dynamic D { f.out[x, y | 0] = f.in[x, y | 0]; }
gauge G -> (real value) { value = f.in[x, y | 0]; }
node_classes { node_class B(I, D, G); node_class S(I, G); }
geometry { nodes[:, :] = B; nodes[2:10, 7:14] = S; }
"""
    text = emit(tmp_path, source, 'gpu_cuda_cpp', '.cu', None)
    copy = text.split('__global__ void gelb_static_buffer_copy()', 1)[1].split('\n}', 1)[0]
    # Unequal extents and bounds distinguish the two axes. Both guards must
    # precede storage access, including threads outside the partial blocks.
    grid_guard = 'if (g_x >= 17 || g_y >= 23) return;'
    class_guard = 'if (!((g_x >= 2 && g_x <= 10 && g_y >= 7 && g_y <= 14))) return;'
    assert grid_guard in copy
    assert class_guard in copy
    assert 'gelb_nc_map' not in copy
    assert copy.index(grid_guard) < copy.index(class_guard) < copy.index('_storage[')


def test_cuda_omits_copy_when_no_initialized_static_cells(tmp_path):
    source = """
simulation_description("empty masked class");
lattices { lattice f(1, 1, real, 17, false); }
initializer I { f.out[x | 0] = 1.0; }
dynamic D { f.out[x | 0] = f.in[x | 0]; }
gauge G -> (real value) { value = f.in[x | 0]; }
node_classes { node_class B(I, D, G); node_class EMPTY() masked; }
geometry { nodes[:] = B; nodes[0:0] = EMPTY; }
"""
    assert 'gelb_static_buffer_copy' not in emit(tmp_path, source, 'gpu_cuda_cpp', '.cu', None)
