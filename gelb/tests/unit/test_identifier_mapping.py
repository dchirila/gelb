#!/usr/bin/env python3
"""
Tests for the GeLB -> Fortran identifier mapping utility.

Verifies that collect_identifier_mapping() produces correct structured
data and that format_identifier_mapping() renders it properly.
"""

import pytest
from gelb.tests.test_utils import get_typed_ast
from gelb.utils.identifier_mapping import (
    collect_identifier_mapping, format_identifier_mapping, uname
)


def _get_sections(code):
    """Run the full frontend pipeline and collect mapping sections."""
    ast = get_typed_ast(code)
    return collect_identifier_mapping(ast)


def _find_section(sections, title_prefix):
    """Find a section whose title starts with the given prefix."""
    for s in sections:
        if s['title'].startswith(title_prefix):
            return s
    return None


def _gelb_names(section):
    """Extract just the GeLB names from a section."""
    return [g for g, _ in section['entries']]


# -- Minimal scaffolding --

_1D_PROGRAM = """
simulation_description("test");
global_constants {{ const int N = 32; const real TAU = 0.6; }}
lattices {{ lattice f(1, 1, int, 32, false); }}
{extra}
initializer Init {{ f.out[x | 0] = 0; }}
dynamic Dyn {{ f.out[x | 0] = f.in[x | 0]; }}
gauge Out -> (int val) {{ val = f.in[x | 0]; }}
node_classes {{ node_class BULK(Init, Dyn, Out); }}
geometry {{ nodes[:] = BULK; }}
"""

_2D_PROGRAM = """
simulation_description("test");
lattices { lattice f(2, 1, int, {32, 32}, {false, false}); }
initializer Init { f.out[x, y | 0] = 0; }
dynamic Dyn { f.out[x, y | 0] = f.in[x, y | 0]; }
gauge Out -> (int val) { val = f.in[x, y | 0]; }
node_classes { node_class BULK(Init, Dyn, Out); }
geometry { nodes[:,:] = BULK; }
"""


class TestImplicitSymbols:
    def test_1d_has_x_and_nx(self):
        sections = _get_sections(_1D_PROGRAM.format(extra=''))
        s = _find_section(sections, 'Implicit')
        assert s is not None
        names = _gelb_names(s)
        assert 'x' in names
        assert 'Nx' in names
        assert 'y' not in names

    def test_2d_has_xy_and_nxny(self):
        sections = _get_sections(_2D_PROGRAM)
        s = _find_section(sections, 'Implicit')
        names = _gelb_names(s)
        assert 'x' in names and 'y' in names
        assert 'Nx' in names and 'Ny' in names
        assert 'z' not in names


class TestGlobalConstants:
    def test_constants_listed(self):
        sections = _get_sections(_1D_PROGRAM.format(extra=''))
        s = _find_section(sections, 'Global constants')
        assert s is not None
        names = _gelb_names(s)
        assert 'N' in names
        assert 'TAU' in names


class TestLattices:
    def test_lattice_listed(self):
        sections = _get_sections(_1D_PROGRAM.format(extra=''))
        s = _find_section(sections, 'Lattices')
        assert s is not None
        assert ('f', uname('f')) in s['entries']


class TestFunctions:
    def test_function_params_listed(self):
        code = _1D_PROGRAM.format(extra="""
        function AddOne(int a) -> (int result) {
            result = a + 1;
        }
        """)
        sections = _get_sections(code)
        s = _find_section(sections, 'Function AddOne')
        assert s is not None
        names = _gelb_names(s)
        assert 'a' in names
        assert 'result' in names


class TestBlockLocals:
    def test_initializer_locals(self):
        code = """
        simulation_description("test");
        lattices { lattice f(1, 1, int, 32, false); }
        initializer Init { int tmp; tmp = 5; f.out[x | 0] = tmp; }
        dynamic Dyn { f.out[x | 0] = f.in[x | 0]; }
        gauge Out -> (int val) { val = f.in[x | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:] = BULK; }
        """
        sections = _get_sections(code)
        s = _find_section(sections, 'Initializer Init')
        assert s is not None
        assert 'tmp' in _gelb_names(s)

    def test_gauge_outputs_listed(self):
        sections = _get_sections(_1D_PROGRAM.format(extra=''))
        s = _find_section(sections, 'Gauge Out')
        assert s is not None
        assert 'val' in _gelb_names(s)


class TestInlinedNamesFiltered:
    def test_compiler_generated_names_excluded(self):
        """Names from function inlining (starting with __) should be filtered."""
        code = """
        simulation_description("test");
        lattices { lattice f(2, 9, real, {32, 32}, {false, false}); }
        function Eq(real rho) -> (real feq) {
            feq = rho;
        }
        initializer Init {
            real rho;
            rho = 1.0;
            f.out[x, y | 0] = Eq(rho);
        }
        dynamic Dyn { f.out[x, y | :] = f.in[x, y | :]; }
        gauge Out -> (real val) { val = f.in[x, y | 0]; }
        node_classes { node_class BULK(Init, Dyn, Out); }
        geometry { nodes[:,:] = BULK; }
        """
        sections = _get_sections(code)
        for s in sections:
            for gelb_name, _ in s['entries']:
                assert not gelb_name.startswith('__'), \
                    f"Compiler-generated name '{gelb_name}' should be filtered"


class TestFormatting:
    def test_format_produces_output(self):
        sections = _get_sections(_1D_PROGRAM.format(extra=''))
        text = format_identifier_mapping(sections)
        assert 'Implicit symbols' in text
        assert 'GeLB' in text
        assert 'Fortran' in text
        assert 'g_x' in text

    def test_format_empty_sections(self):
        text = format_identifier_mapping([])
        assert text == ''

    def test_uname_encoding(self):
        assert uname('x') == 'g_x'
        assert uname('TAU') == 'g__t_a_u'
        assert uname('f') == 'g_f'
        assert uname('M_INV') == 'g__m___i_n_v'
