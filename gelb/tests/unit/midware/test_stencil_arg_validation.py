#!/usr/bin/env python3
"""Unit tests for the stencil-vector argument validation pass.

Validates that arguments to ``upstream_dfs(f, x, y, {EX, EY})`` and
``bounce_back_dfs(f, x, y, {EX, EY})`` are sensible:

  * each velocity-vector identifier resolves to a 1-D global-constant
    array,
  * the array length matches the lattice's q,
  * the number of velocity vectors matches the lattice's d,
  * the folded element values are integer-valued (so they translate
    directly to neighbour-cell offsets in every backend's stencil
    codegen).

Pre-this-pass these errors surfaced as backend ``RuntimeError`` /
``ValueError`` deep in codegen, with no source-line context.  The
validation pass raises ``GeLBExStencilError`` at midware time with
the offending call site's ``code_range``, so the standard error
reporter highlights the bad line.
"""

from pathlib import Path

import pytest

from gelb.frontend.stage1_frontend import promote_types, validate_types
from gelb.midware.ConstantFoldingVisitor import ConstantFoldingVisitor
from gelb.midware.StencilArgValidator import (
    validate_streaming_intrinsic_args,
)
from gelb.tests.test_utils import get_typed_ast
from gelb.utils.exceptions import GeLBExStencilError


_REPO_ROOT = Path(__file__).resolve().parents[4]


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _validate(gelb_code: str):
    """Run the full pipeline up through fold_constants, then call
    the validator.  Re-raises any GeLBExStencilError to the caller."""
    ast = get_typed_ast(gelb_code)
    ast = promote_types(ast)
    validate_types(ast)
    folded = ConstantFoldingVisitor().visit(ast, ast)
    validate_streaming_intrinsic_args(folded)
    return folded


def _wrap_d2q9_program(globals_, dynamic_body):
    """Wrap a global-constants block + dynamic-block body in a
    minimal D2Q9 program shell."""
    return (
        'simulation_description("test");\n'
        'global_constants {\n'
        '    const int N = 16;\n'
        f'{globals_}\n'
        '}\n'
        'lattices { lattice f(2, 9, real, {N, N}, {true, true}); }\n'
        'function Eq(real rho) -> (array[real, 9] feq) '
        '{ feq = W * rho; }\n'
        'initializer Init { f.out[x, y | :] = Eq(1.0); }\n'
        'dynamic Step {\n'
        f'{dynamic_body}\n'
        '}\n'
        'gauge G -> (real rho) { rho = sum(f.in[x, y | :]); }\n'
        'node_classes { node_class BULK(Init, Step, G); }\n'
        'geometry { nodes[:, :] = BULK; }\n'
    )


_VALID_D2Q9_GLOBALS = (
    '    const array[real, 9] EX = {0.0, 1.0, 0.0, -1.0, 0.0, 1.0, -1.0, -1.0, 1.0};\n'
    '    const array[real, 9] EY = {0.0, 0.0, 1.0,  0.0, -1.0, 1.0,  1.0, -1.0, -1.0};\n'
    '    const array[real, 9] W  = {1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, '
    '1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0};'
)


# ----------------------------------------------------------------------
# Happy path: every shipped LBM example validates
# ----------------------------------------------------------------------


def _shipped_lbm_examples():
    """All ``.gelb`` files under examples/lbm/ that should validate
    cleanly.  Used to parametrise the happy-path test."""
    root = _REPO_ROOT / "examples" / "lbm"
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.gelb"))


_LBM_EXAMPLES = _shipped_lbm_examples()


@pytest.mark.parametrize(
    "example_path",
    _LBM_EXAMPLES,
    ids=[str(p.relative_to(_REPO_ROOT)) for p in _LBM_EXAMPLES],
)
def test_shipped_lbm_examples_validate(example_path):
    """Every shipped LBM example uses ``upstream_dfs`` / ``bounce_back_dfs``
    with sensible velocity vectors; the validator must accept all of
    them.  Guards against accidentally tightening the rules in a way
    that breaks current code (in particular: every LBM example
    declares ``array[real, q] EX = {0.0, 1.0, ...}`` with integer-
    valued real literals, and the validator must accept that form
    rather than insisting on ``array[int, q]``)."""
    src = example_path.read_text()
    # Skip examples that don't even parse without explicit constant
    # overrides (unrelated to this validator).  None expected today.
    _validate(src)


# ----------------------------------------------------------------------
# Error cases (D2Q9, since that exercises every code path)
# ----------------------------------------------------------------------


class TestNonIntegerValues:
    """Velocity-vector elements that fold to non-integer reals must
    be rejected with a clear message naming the offending index."""

    def test_fractional_value_in_ex(self):
        bad = (
            '    const array[real, 9] EX = '
            '{0.0, 1.5, 0.0, -1.5, 0.0, 1.0, -1.0, -1.0, 1.0};\n'
            '    const array[real, 9] EY = '
            '{0.0, 0.0, 1.0,  0.0, -1.0, 1.0,  1.0, -1.0, -1.0};\n'
            '    const array[real, 9] W  = '
            '{1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, '
            '1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0};'
        )
        body = (
            '    array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY});\n'
            '    f.out[x, y | :] = fIn;'
        )
        with pytest.raises(GeLBExStencilError) as exc:
            _validate(_wrap_d2q9_program(bad, body))
        msg = str(exc.value.error)
        assert 'EX' in msg
        assert 'not integer-valued' in msg


class TestWrongLength:
    """Velocity-vector array with the wrong number of elements is
    flagged against the lattice's q."""

    def test_too_few_elements(self):
        # 7 elements, but lattice q=9 -> mismatch.
        bad = (
            '    const array[real, 7] EX = '
            '{0.0, 1.0, 0.0, -1.0, 0.0, 1.0, -1.0};\n'
            '    const array[real, 9] EY = '
            '{0.0, 0.0, 1.0,  0.0, -1.0, 1.0,  1.0, -1.0, -1.0};\n'
            '    const array[real, 9] W  = '
            '{1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, '
            '1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0};'
        )
        body = (
            '    array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY});\n'
            '    f.out[x, y | :] = fIn;'
        )
        with pytest.raises(GeLBExStencilError) as exc:
            _validate(_wrap_d2q9_program(bad, body))
        msg = str(exc.value.error)
        assert "EX" in msg
        assert ('7 elements' in msg) or ("q=9" in msg)


class TestWrongDimensionCount:
    """Number of velocity-vector entries must match the lattice's d."""

    def test_three_vectors_for_2d_lattice(self):
        # Three velocity vectors passed to a D2 lattice -> reject.
        triple_globals = _VALID_D2Q9_GLOBALS + (
            '\n    const array[real, 9] EZ = '
            '{0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};'
        )
        body = (
            '    array[real, 9] fIn = upstream_dfs(f, x, y, '
            '{EX, EY, EZ});\n'
            '    f.out[x, y | :] = fIn;'
        )
        with pytest.raises(GeLBExStencilError) as exc:
            _validate(_wrap_d2q9_program(triple_globals, body))
        msg = str(exc.value.error)
        assert ("3 velocity" in msg.lower()
                or "expects 2 velocity" in msg.lower()
                or "got 3" in msg.lower())


class TestNonGlobalConstantArg:
    """Argument that doesn't resolve to a global constant (e.g. a
    local variable) is rejected with a hint pointing at
    ``global_constants``."""

    def test_local_variable_as_velocity(self):
        body = (
            '    array[real, 9] local_ex = '
            '{0.0, 1.0, 0.0, -1.0, 0.0, 1.0, -1.0, -1.0, 1.0};\n'
            '    array[real, 9] fIn = upstream_dfs(f, x, y, '
            '{local_ex, EY});\n'
            '    f.out[x, y | :] = fIn;'
        )
        with pytest.raises(GeLBExStencilError) as exc:
            _validate(_wrap_d2q9_program(_VALID_D2Q9_GLOBALS, body))
        msg = str(exc.value.error)
        assert 'local_ex' in msg
        assert 'global constant' in msg.lower()


# ----------------------------------------------------------------------
# Integer-valued reals must still be accepted
# ----------------------------------------------------------------------


def test_real_array_with_integer_valued_floats_validates():
    """Every shipped LBM example uses ``array[real, q] EX = {0.0,
    1.0, 0.0, -1.0, ...}``.  The validator must accept integer-
    valued reals (not insist on ``array[int, q]``)."""
    body = (
        '    array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY});\n'
        '    f.out[x, y | :] = fIn;'
    )
    # Should not raise.
    _validate(_wrap_d2q9_program(_VALID_D2Q9_GLOBALS, body))
