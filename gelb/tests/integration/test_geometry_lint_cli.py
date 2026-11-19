"""CLI integration tests for compiler-surfaced geometry lint warnings."""

from __future__ import annotations

import json

import pytest

from click.testing import CliRunner

from gelb.gelbc import cli as gelbc_cli


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
    from gelb.compiler_pipeline import PipelineOptions, PipelineProfile, compile_source
    from gelb.backends.stage3_backend_cpu_fortran_serial import FortranCodeGenerator, generate_fortran
    from gelb.backends.stage3_backend_cpu_highway import HighwayCodeGenerator, generate_cpu_highway
    from gelb.backends.stage3_backend_gpu_cuda_cpp import CudaCppCodeGenerator, generate_cuda_cpp

    result = compile_source(_BACKEND_HANDOFF_SOURCE, PipelineProfile.CODEGEN,
                            PipelineOptions(require_stencils=True, require_geometry=True))
    for generate in (FortranCodeGenerator, HighwayCodeGenerator, CudaCppCodeGenerator,
                     generate_fortran, generate_cpu_highway, generate_cuda_cpp):
        with pytest.raises(ValueError, match='BackendContext is required'):
            generate(result.ast)
        with pytest.raises(ValueError, match='BackendContext is required'):
            generate(result.ast, backend_context=None)


def test_backends_reuse_backend_context(monkeypatch):
    from gelb.compiler_pipeline import (
        PipelineOptions, PipelineProfile, compile_source, build_backend_context,
    )
    from gelb.midware.c_family_lowering import prepare_c_family_ast
    from gelb.backends.stage3_backend_cpu_fortran_serial import FortranCodeGenerator
    from gelb.backends.stage3_backend_cpu_highway import HighwayCodeGenerator
    from gelb.backends.stage3_backend_gpu_cuda_cpp import CudaCppCodeGenerator

    result = compile_source(_BACKEND_HANDOFF_SOURCE, PipelineProfile.CODEGEN,
                            PipelineOptions(require_stencils=True, require_geometry=True))
    result.ast = prepare_c_family_ast(result.ast)
    context = build_backend_context(result)

    def fail_analysis(*args, **kwargs):
        raise AssertionError('backend must reuse the supplied analysis')

    for name in ('gelb.midware.ast_eval.collect_lattice_info',
                 'gelb.midware.ast_eval.eval_const_expr',
                 'gelb.midware.geometry.resolve_geometry',
                 'gelb.midware.stage2_midware.extract_stencils',
                 'gelb.backends.gauge_outputs.collect_gauge_outputs'):
        monkeypatch.setattr(name, fail_analysis)
    for generator in (FortranCodeGenerator, HighwayCodeGenerator, CudaCppCodeGenerator):
        backend = generator(result.ast, backend_context=context)
        assert backend._lattice_info is context.lattice_info
        assert backend._stencils is context.stencils
        assert backend.backend_context.geometry is result.geometry
        backend.generate()
