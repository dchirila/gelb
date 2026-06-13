#!/usr/bin/env python3
"""Tests for LatticeAccessContextValidator."""

import pytest

from gelb.frontend.stage1_frontend import get_ast, validate_lattice_access_context
from gelb.tests.test_utils import minimal_gelb_program_1d, minimal_gelb_program_2d
from gelb.utils.exceptions import GeLBExTypeError
import gelb.utils.config as config


def _validate(gelb_code):
    """Parse and run lattice access validation."""
    config.GELB_SRC_RAW = gelb_code
    ast = get_ast("gelb_program", gelb_code)
    validate_lattice_access_context(ast)
    return ast


class TestValidCases:
    """Programs with correct lattice access patterns should pass."""

    def test_fout_in_initializer(self):
        code = minimal_gelb_program_1d(initializer_content="f.out[x | 0] = 1;")
        _validate(code)

    def test_fout_in_dynamic(self):
        code = minimal_gelb_program_1d(dynamic_content="f.out[x | 0] = f.in[x | 0];")
        _validate(code)

    def test_fin_in_dynamic(self):
        code = minimal_gelb_program_1d(dynamic_content="f.out[x | 0] = f.in[x | 0];")
        _validate(code)

    def test_fin_in_gauge(self):
        code = minimal_gelb_program_1d(gauge_content="val = f.in[x | 0];")
        _validate(code)

    def test_all_valid_patterns(self):
        """A complete program with all valid access patterns."""
        code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = 0;",
            dynamic_content="f.out[x | 0] = f.in[x | 0];",
            gauge_content="val = f.in[x | 0];",
        )
        _validate(code)

    def test_valid_2d(self):
        code = minimal_gelb_program_2d(
            initializer_content="f.out[x, y | 0] = 0;",
            dynamic_content="f.out[x, y | 0] = f.in[x, y | 0];",
            gauge_content="val = f.in[x, y | 0];",
        )
        _validate(code)


class TestInvalidFoutInGauge:
    """f.out[...] in gauge should be rejected."""

    def test_fout_in_gauge_1d(self):
        code = minimal_gelb_program_1d(gauge_content="f.out[x | 0] = 1;")
        with pytest.raises(GeLBExTypeError, match="f.out"):
            _validate(code)

    def test_fout_in_gauge_2d(self):
        code = minimal_gelb_program_2d(gauge_content="f.out[x, y | 0] = 1;")
        with pytest.raises(GeLBExTypeError, match="f.out"):
            _validate(code)


class TestInvalidFinInInitializer:
    """f.in[...] in initializer should be rejected."""

    def test_fin_in_initializer_1d(self):
        code = minimal_gelb_program_1d(
            initializer_content="f.out[x | 0] = f.in[x | 0];"
        )
        with pytest.raises(GeLBExTypeError, match="f.in"):
            _validate(code)

    def test_fin_in_initializer_2d(self):
        code = minimal_gelb_program_2d(
            initializer_content="f.out[x, y | 0] = f.in[x, y | 0];"
        )
        with pytest.raises(GeLBExTypeError, match="f.in"):
            _validate(code)
