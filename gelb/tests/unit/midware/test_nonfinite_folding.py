#!/usr/bin/env python3
"""Constants that overflow or are invalid fold to their IEEE values.

``sqrt(-1.0)``, ``log(0.0)`` and ``exp(1000.0)`` written as constants,
as global constants, in constant arrays and as block-local constants
once passed ``gelbc`` unfolded and failed in gfortran (a constant
argument outside the intrinsic's domain), in g++ and nvcc (a
non-constexpr call in a constant), or lost their declaration (a
surviving local ``const``).

Now the folder runs in the evaluator's IEEE mode and writes the value
the run time would give, a NaN or a signed infinity, into the literal
(user manual, Numerical semantics: Constant folding); every surviving
block-local ``const`` is lowered to a typed declaration; and the
backends emit a non-finite literal as an explicit special value (user
manual, Numerical semantics: Special values).  The native tests here
run these programs through ``scripts/gelb-run`` on the three backends
and read the special values back from the output file.
"""

import math

import numpy as np
import pytest
from click.testing import CliRunner

from gelb.compiler_pipeline import (
    PipelineOptions, PipelineProfile, compile_source)
from gelb.gelb_ast.ASTNodes import (
    Array1DLiteral_N, ConstantDefinitionStmt_N, Identifier_N, Node_N,
    RealLiteral_N, TypePromotionNode_N, VariableAssignmentStmt_N,
    VariableDeclarationStmt_N)
from gelb.gelbc import cli as gelbc_cli
from gelb.tests.integration.test_tutorial_regressions import (
    BACKENDS, run_source)


def program(gauge, *, globals="", outputs="real v"):
    """A one-cell program, with the construct under test."""
    return (
        'simulation_description("native diagnostic check");\n'
        f'{globals}\n'
        'lattices { lattice u(1,1,real,4,false); }\n'
        'initializer I { u.out[x | 0] = 1.0; }\n'
        'dynamic D { u.out[x | 0] = u.in[x | 0]; }\n'
        f'gauge G -> ({outputs}) {{ {gauge} }}\n'
        'node_classes { node_class BULK(I,D,G); }\n'
        'geometry { nodes[:] = BULK; }\n'
    )


# One program per place a non-finite constant can be written: directly,
# as a global constant, in a global constant array, as a block-local const.
DIRECT_SQRT_DOMAIN = program("v = sqrt(-1.0);")
GLOBAL_CONST_OVERFLOW = program(
    "v = a;", globals="global_constants {const real a = exp(1000.0);}")
GLOBAL_ARRAY_DOMAIN = program(
    "v = a[0];",
    globals="global_constants {const array[real32, 2] a = {sqrt(-1.0), 1.0};}")
LOCAL_CONST_NARROW_OVERFLOW = program("const real32 a = real32(1.0e300); v = a;")

NONFINITE_PROGRAMS = [
    pytest.param(DIRECT_SQRT_DOMAIN, math.nan, id="direct sqrt(-1.0)"),
    pytest.param(GLOBAL_CONST_OVERFLOW, math.inf, id="global exp(1000.0)"),
    pytest.param(GLOBAL_ARRAY_DOMAIN, math.nan, id="real32 array sqrt(-1.0)"),
    pytest.param(LOCAL_CONST_NARROW_OVERFLOW, math.inf, id="local real32(1.0e300)"),
]

# One program with every construct, for the native runs.
EVERYTHING = program(
    """
    const real32 w = real32(1.0e300);
    const real q = exp(1000.0);
    s = sqrt(-1.0);
    l = log(0.0);
    e = exp(1000.0);
    a = A;
    b = B;
    c0 = C[0];
    f0 = F[0];
    n = w;
    m = q;
    p = (-8.0)^(1.0/3.0);
    r = sum(C);
    """,
    globals="""global_constants {
    const real A = exp(1000.0);
    const real B = 1.0e300 * 1.0e300;
    const array[real, 2] C = {exp(1000.0), 1.0};
    const array[real32, 2] F = {sqrt(-1.0), 2.0};
}""",
    outputs="real s, real l, real e, real a, real b, real c0, real f0,"
            " real n, real m, real p, real r")
EVERYTHING_EXPECTED = {
    "s": math.nan, "l": -math.inf, "e": math.inf, "a": math.inf,
    "b": math.inf, "c0": math.inf, "f0": math.nan, "n": math.inf,
    "m": math.inf, "p": math.nan, "r": math.inf,
}


def _same(actual, expected):
    actual = np.asarray(actual, dtype=float)
    if math.isnan(expected):
        return bool(np.isnan(actual).all())
    return bool((actual == expected).all())


# ---------------------------------------------------------------------------
# the folder
# ---------------------------------------------------------------------------

def _ast(source):
    return compile_source(source, PipelineProfile.CODEGEN,
                          PipelineOptions(emit_warnings=False)).ast


def _unwrapped(node):
    while isinstance(node, TypePromotionNode_N):
        node = node.expr
    return node


def _gauge_value(ast, name):
    """The folded right-hand side assigned to the gauge output ``name``."""
    for stmt in ast.gauges.elements[0].stmts.elements:
        if isinstance(stmt, VariableAssignmentStmt_N) \
                and getattr(stmt.lhs, 'name', None) == name:
            return _unwrapped(stmt.rhs)
    raise AssertionError(f"no assignment to {name}")


def _walk(node):
    if node is None:
        return
    yield node
    if isinstance(node, Node_N):
        for child in node.get_children():
            if isinstance(child, Node_N):
                yield from _walk(child)


@pytest.mark.parametrize("expr, expected, width", [
    ("sqrt(-1.0)", math.nan, "real"),
    ("log(0.0)", -math.inf, "real"),
    ("log(-1.0)", math.nan, "real"),
    ("exp(1000.0)", math.inf, "real"),
    ("(-8.0)^(1.0/3.0)", math.nan, "real"),
    ("10.0^400.0", math.inf, "real"),
    ("1.0e300 * 1.0e300", math.inf, "real"),
    ("-(1.0e300 * 1.0e300)", -math.inf, "real"),
    ("1.0e308 + 1.0e308", math.inf, "real"),
    ("real32(1.0e300)", math.inf, "real32"),
    ("exp(real32(100.0))", math.inf, "real32"),
    ("sum({1.0e308, 1.0e308})", math.inf, "real"),
    ("dot_prod({1.0e308, 0.0}, {10.0, 0.0})", math.inf, "real"),
])
def test_a_constant_outside_the_domain_or_range_folds_to_its_ieee_value(
        expr, expected, width):
    value = _gauge_value(_ast(program(f"v = {expr};")), "v")
    assert isinstance(value, RealLiteral_N), value
    assert _same(value.value, expected)
    assert value.inferred_type.element_dtype == width


def test_global_constants_fold_to_special_values_and_so_do_their_uses():
    ast = _ast(EVERYTHING)
    folded = {}
    for stmt in ast.global_constants.stmts.elements:
        folded[stmt.name.name] = _unwrapped(stmt.value)
    assert _same(folded["A"].value, math.inf)
    assert _same(folded["B"].value, math.inf)
    assert isinstance(folded["C"], Array1DLiteral_N)
    assert _same(folded["C"].value.elements[0].value, math.inf)
    assert folded["C"].value.elements[1].value == 1.0
    assert isinstance(folded["F"], Array1DLiteral_N)
    assert _same(folded["F"].value.elements[0].value, math.nan)
    # a constant array's elements sit under the promotion to the
    # declared width, as every constant array's do
    for stmt in ast.global_constants.stmts.elements:
        if stmt.name.name == "F":
            assert stmt.value.inferred_type.element_dtype == "real32"
    # the scalar uses are the values (an indexed read of a constant
    # array, c0 and f0, stays a read of the emitted array, as before)
    for name, expected in EVERYTHING_EXPECTED.items():
        if name in ("c0", "f0"):
            continue
        value = _gauge_value(ast, name)
        assert isinstance(value, RealLiteral_N), (name, value)
        assert _same(value.value, expected), name


def test_a_block_local_const_is_lowered_to_a_typed_declaration():
    ast = _ast(program(
        "const real32 w = real32(1.0e300); const real q = 2.0 + 1.0;"
        " v = w; k = q;", outputs="real v, real k"))
    blocks = list(ast.initializers.elements) + list(ast.dynamics.elements) \
        + list(ast.gauges.elements)
    assert not any(isinstance(n, ConstantDefinitionStmt_N)
                   for block in blocks for n in _walk(block.stmts))
    decls = {stmt.name.name: stmt
             for stmt in ast.gauges.elements[0].stmts.elements
             if isinstance(stmt, VariableDeclarationStmt_N)}
    assert decls["w"].data_type.element_dtype == "real32"
    assert _same(_unwrapped(decls["w"].initial_value).value, math.inf)
    assert decls["q"].data_type.element_dtype == "real"
    assert _unwrapped(decls["q"].initial_value).value == 3.0
    # the uses were substituted by the folder
    assert _same(_gauge_value(ast, "v").value, math.inf)
    assert _gauge_value(ast, "k").value == 3.0


def test_a_local_const_that_does_not_fold_is_lowered_too():
    # a draw is the one initializer the frontend accepts for a local
    # const that the folder cannot evaluate
    ast = _ast(program("const real a = random(); v = a;"))
    stmts = ast.gauges.elements[0].stmts.elements
    [decl] = [s for s in stmts if isinstance(s, VariableDeclarationStmt_N)
              and s.name.name == "a"]
    assert decl.initial_value is not None
    assert not any(isinstance(n, ConstantDefinitionStmt_N) for n in _walk(ast.gauges))
    assert isinstance(_gauge_value(ast, "v"), Identifier_N)


@pytest.mark.parametrize("source, expected", NONFINITE_PROGRAMS)
@pytest.mark.parametrize("backend", ["cpu_fortran_serial", "cpu_highway", "gpu_cuda_cpp"])
def test_the_nonfinite_constants_pass_gelbc_with_empty_diagnostics(
        tmp_path, source, expected, backend):
    path = tmp_path / "case.gelb"
    path.write_text(source)
    result = CliRunner().invoke(gelbc_cli, [str(path), "--diagnostics-json"])
    assert result.exit_code == 0, result.output
    assert '"diagnostics": []' in result.output
    out = tmp_path / f"out_{backend}.src"
    result = CliRunner().invoke(
        gelbc_cli, [str(path), "--backend", backend, "-o", str(out)])
    assert result.exit_code == 0, result.output
    text = out.read_text()
    # never the invalid call as a constant argument
    assert "sqrt(-1.0" not in text and "exp(1000.0" not in text


# ---------------------------------------------------------------------------
# natively, through gelb-run, on three backends (the backends' emission)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source, expected", NONFINITE_PROGRAMS)
@pytest.mark.parametrize("backend", ["cpu_fortran_serial", "cpu_highway", "gpu_cuda_cpp"])
def test_a_special_value_is_never_spelled_out(tmp_path, source, expected, backend):
    """The backends' side: a non-finite literal is emitted as an
    explicit special value, never as Python's spelling."""
    path = tmp_path / "case.gelb"
    path.write_text(source)
    out = tmp_path / f"out_{backend}.src"
    result = CliRunner().invoke(
        gelbc_cli, [str(path), "--backend", backend, "-o", str(out)])
    assert result.exit_code == 0, result.output
    text = out.read_text()
    assert "inf.0" not in text and "nan.0" not in text, text
    assert " inf;" not in text and " inff;" not in text, text

@pytest.mark.parametrize("source, expected", NONFINITE_PROGRAMS)
@pytest.mark.parametrize("backend", BACKENDS)
def test_the_nonfinite_constants_run_natively(tmp_path, backend, source, expected):
    data = run_source(tmp_path, backend, source)
    assert _same(data["v"], expected), data["v"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_every_special_value_reaches_the_output(tmp_path, backend):
    data = run_source(tmp_path, backend, EVERYTHING)
    for name, expected in EVERYTHING_EXPECTED.items():
        assert _same(data[name], expected), (name, data[name])
