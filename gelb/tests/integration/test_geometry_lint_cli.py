"""CLI integration tests for compiler-surfaced geometry lint warnings."""

from __future__ import annotations

import json

from click.testing import CliRunner

from gelb.compiler_pipeline import BackendContext
from gelb.gelbc import cli as gelbc_cli
from gelb.midware.ast_eval import collect_lattice_info
from gelb.midware.geometry import resolve_geometry
from gelb.midware.stage2_midware import extract_stencils
from gelb.tests.test_utils import get_fully_validated_ast


_DISCONNECTED_SOURCE = """
simulation_description("disconnected cli lint");
global_constants {
    const int N = 16;
}
lattices { lattice f(2, 9, real, {N, N}, {true, true}); }
initializer Init { f.out[x, y | :] = 1.0; }
dynamic D { f.out[x, y | :] = f.in[x, y | :]; }
gauge G -> (real v) { v = sum(f.in[x, y | :]); }
function ManyDots(int x, int y) -> (bool hit) {
    hit = ((x == 2)  && (y == 2))
       || ((x == 5)  && (y == 5))
       || ((x == 8)  && (y == 8))
       || ((x == 11) && (y == 11))
       || ((x == 14) && (y == 14));
}
node_classes {
    node_class FLUID(Init, D, G);
    node_class DOT() masked;
}
geometry {
    nodes[:, :] = FLUID;
    nodes[where ManyDots(x, y)] = DOT;
}
"""


_BACKEND_HANDOFF_SOURCE = """
simulation_description("backend geometry handoff");
global_constants { const int N = 8; }
lattices { lattice f(2, 9, real, {N, N}, {true, true}); }
initializer Init { f.out[x, y | :] = 1.0; }
dynamic D { f.out[x, y | :] = f.in[x, y | :]; }
gauge G -> (real v) { v = sum(f.in[x, y | :]); }
node_classes { node_class FLUID(Init, D, G); }
geometry { nodes[:, :] = FLUID; }
"""


def _write_source(tmp_path):
    source_path = tmp_path / "disconnected.gelb"
    source_path.write_text(_DISCONNECTED_SOURCE)
    return source_path


def _compile_args(source_path, output_path):
    return [
        str(source_path),
        "--backend",
        "cpu_fortran_serial",
        "--output",
        str(output_path),
    ]


def test_gelbc_emits_geometry_lint_warning_by_default(tmp_path):
    source_path = _write_source(tmp_path)
    output_path = tmp_path / "out.f90"

    result = CliRunner().invoke(
        gelbc_cli,
        _compile_args(source_path, output_path),
    )

    assert result.exit_code == 0, result.output + result.stderr
    assert output_path.exists()
    assert "disconnected regions" in result.stderr
    assert "Node class 'DOT'" in result.stderr


def test_gelbc_no_geometry_lint_suppresses_warning(tmp_path):
    source_path = _write_source(tmp_path)
    output_path = tmp_path / "out.f90"

    result = CliRunner().invoke(
        gelbc_cli,
        _compile_args(source_path, output_path) + ["--no-geometry-lint"],
    )

    assert result.exit_code == 0, result.output + result.stderr
    assert output_path.exists()
    assert "disconnected regions" not in result.stderr


def test_diagnostics_json_includes_geometry_lint_warning(tmp_path):
    source_path = _write_source(tmp_path)

    result = CliRunner().invoke(
        gelbc_cli,
        [str(source_path), "--diagnostics-json"],
    )

    assert result.exit_code == 0, result.output + result.stderr
    payload = json.loads(result.output)
    [warning] = [
        diagnostic for diagnostic in payload["diagnostics"]
        if diagnostic["severity"] == "warning"
        and "disconnected regions" in diagnostic["message"]
        and "DOT" in diagnostic["message"]
    ]
    # It points at DOT's node_class statement (0-based line).
    dot_line = next(i for i, line in enumerate(_DISCONNECTED_SOURCE.splitlines())
                    if "node_class DOT" in line)
    assert warning["range"]["startLine"] == dot_line


def test_diagnostics_json_no_geometry_lint_suppresses_warning(tmp_path):
    source_path = _write_source(tmp_path)

    result = CliRunner().invoke(
        gelbc_cli,
        [str(source_path), "--diagnostics-json", "--no-geometry-lint"],
    )

    assert result.exit_code == 0, result.output + result.stderr
    payload = json.loads(result.output)
    assert not any(
        "disconnected regions" in diagnostic["message"]
        for diagnostic in payload["diagnostics"]
    )


def test_backends_reuse_resolved_geometry(monkeypatch):
    ast = get_fully_validated_ast(_BACKEND_HANDOFF_SOURCE)
    geometry = resolve_geometry(ast)

    def fail_resolve_geometry(_ast):
        raise AssertionError("backend should reuse the supplied geometry")

    from gelb.backends.stage3_backend_cpu_fortran_serial import (
        FortranCodeGenerator,
    )
    monkeypatch.setattr(
        "gelb.midware.geometry.resolve_geometry",
        fail_resolve_geometry,
    )
    fortran = FortranCodeGenerator(ast, resolved_geometry=geometry)
    fortran._resolve_geometry_via_midware()

    from gelb.backends import stage3_backend_cpu_highway as highway_backend
    monkeypatch.setattr(
        highway_backend,
        "resolve_geometry",
        fail_resolve_geometry,
    )

    highway = highway_backend.HighwayCodeGenerator(
        ast,
        resolved_geometry=geometry,
    )
    assert highway._geom is geometry

    from gelb.backends.stage3_backend_gpu_cuda_cpp import CudaCppCodeGenerator
    cuda = CudaCppCodeGenerator(ast, resolved_geometry=geometry)
    assert cuda._geom is geometry


def test_backends_reuse_backend_context(monkeypatch):
    ast = get_fully_validated_ast(_BACKEND_HANDOFF_SOURCE)
    geometry = resolve_geometry(ast)
    lattice_info = collect_lattice_info(ast)
    # Real stencils, not a bare sentinel: a backend asks them for the
    # periodic and write reach while deciding its storage layout (CBT
    # gates on both), so a typeless object crashes ``__init__`` wherever
    # ``auto`` resolves to CBT.  Identity still proves the reuse.
    context = BackendContext(
        ast=ast,
        lattice_info=lattice_info,
        stencils=extract_stencils(ast),
        geometry=geometry,
    )

    def fail_collect_lattice_info(_ast):
        raise AssertionError("backend should reuse supplied lattice info")

    def fail_resolve_geometry(_ast):
        raise AssertionError("backend should reuse supplied geometry")

    from gelb.backends import stage3_backend_cpu_fortran_serial as fortran_backend
    monkeypatch.setattr(
        fortran_backend,
        "collect_lattice_info",
        fail_collect_lattice_info,
    )
    monkeypatch.setattr(
        "gelb.midware.geometry.resolve_geometry",
        fail_resolve_geometry,
    )
    fortran = fortran_backend.FortranCodeGenerator(
        ast,
        backend_context=context,
    )
    assert fortran._lattice_info is lattice_info
    assert fortran._stencils is context.stencils
    fortran._resolve_geometry_via_midware()

    from gelb.backends import stage3_backend_cpu_highway as highway_backend
    monkeypatch.setattr(
        highway_backend,
        "collect_lattice_info",
        fail_collect_lattice_info,
    )
    monkeypatch.setattr(
        highway_backend,
        "resolve_geometry",
        fail_resolve_geometry,
    )

    highway = highway_backend.HighwayCodeGenerator(
        ast,
        backend_context=context,
    )
    assert highway._lattice_info is lattice_info
    assert highway._stencils is context.stencils
    assert highway._geom is geometry

    from gelb.backends.stage3_backend_gpu_cuda_cpp import CudaCppCodeGenerator
    cuda = CudaCppCodeGenerator(ast, backend_context=context)
    assert cuda._lattice_info is lattice_info
    assert cuda._stencils is context.stencils
    assert cuda._geom is geometry
