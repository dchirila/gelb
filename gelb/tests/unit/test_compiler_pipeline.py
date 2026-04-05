#!/usr/bin/env python3
"""Tests for canonical compiler pipeline profiles."""

from gelb.compiler_pipeline import (
    PipelineOptions, PipelineProfile, build_backend_context, compile_file)
from gelb.tests.test_utils import minimal_gelb_program_1d


_FRONTEND_PREFIX = (
    "parse",
    "validate_ast_root",
    "validate_lattice_access_context",
    "validate_block_signatures",
    "prevent_symbol_ref_implicit_clashes",
    "build_symbols_tables",
    "prevent_symbol_def_implicit_clashes",
)

_FRONTEND_TYPED_SUFFIX = (
    "add_implicit_symbols",
    "validate_fixed_geometry",
    "validate_global_constant_initializers",
    "resolve_all_constants",
    "resolve_ranges",
    "infer_types",
    "promote_types",
    "validate_types",
    "validate_constant_assignments",
    "validate_lattice_consistency",
    "validate_node_classes",
    "initial_validation_geometry",
    "validate_midware_input",
    "fold_constants",
    "validate_division_by_zero",
    "lower_local_constants",
)

_CODEGEN_MIDWARE_SUFFIX = (
    "validate_streaming_intrinsic_args",
    "sequence_draws",
    "inline_functions",
    "hoist_intrinsic_args",
    "extract_stencils",
    "validate_initializer_coverage",
    "warn_writeonly_dynamics",
    "warn_unused_lattices",
    # on the resolved map, the one path every compilation takes
    "resolve_geometry",
    "validate_boundary_access",
    "validate_write_destinations",
    "validate_df_coverage",
)

_OPTIMIZATION_PASSES = (
    "collinearity_rewrite",
    "scalar_block_cse",
    "slice_df_expansion",
)


def _write_program(tmp_path):
    path = tmp_path / "minimal.gelb"
    path.write_text(minimal_gelb_program_1d(), encoding="utf-8")
    return path


def test_codegen_profile_pass_sequence_without_optimizations(tmp_path):
    result = compile_file(
        _write_program(tmp_path),
        PipelineProfile.CODEGEN,
        PipelineOptions(
            enable_collinearity_rewrite=False,
            enable_scalar_cse=False,
            enable_slice_simplify=False,
            require_stencils=True,
            require_geometry=True,
            geometry_lint=False,
        ),
    )

    assert result.pass_names == (
        *_FRONTEND_PREFIX,
        "detect_function_recursion",
        *_FRONTEND_TYPED_SUFFIX,
        *_CODEGEN_MIDWARE_SUFFIX,
    )
    assert result.stencils is not None
    assert result.geometry is not None


def test_diagnostics_profile_runs_optimization_passes_by_default(tmp_path):
    result = compile_file(
        _write_program(tmp_path),
        PipelineProfile.DIAGNOSTICS,
        PipelineOptions(
            require_stencils=True,
            require_geometry=True,
            geometry_lint=False,
        ),
    )

    assert result.pass_names == (
        *_FRONTEND_PREFIX,
        "detect_function_recursion",
        *_FRONTEND_TYPED_SUFFIX,
        "validate_streaming_intrinsic_args",
        "sequence_draws",
        "inline_functions",
        "hoist_intrinsic_args",
        # The collinearity rewrite is off by default (user manual,
        # Numerical semantics: What the optimizer promises): it
        # re-associates and has no general error bound.
        *_OPTIMIZATION_PASSES[1:],
        *_CODEGEN_MIDWARE_SUFFIX[4:],
    )


def test_the_collinearity_rewrite_runs_only_when_enabled(tmp_path):
    def passes(**options):
        return compile_file(
            _write_program(tmp_path),
            PipelineProfile.DIAGNOSTICS,
            PipelineOptions(require_stencils=True, require_geometry=True,
                            geometry_lint=False, **options),
        ).pass_names

    assert "collinearity_rewrite" not in passes()
    assert "collinearity_rewrite" not in passes(enable_collinearity_rewrite=False)
    enabled = passes(enable_collinearity_rewrite=True)
    assert "collinearity_rewrite" in enabled
    assert enabled.index("collinearity_rewrite") < enabled.index("scalar_block_cse")


def test_program_analysis_profile_preserves_viewer_pass_sequence(tmp_path):
    result = compile_file(
        _write_program(tmp_path),
        PipelineProfile.PROGRAM_ANALYSIS,
        PipelineOptions(require_geometry=True, require_stencils=True),
    )

    assert result.pass_names == (
        *_FRONTEND_PREFIX,
        *_FRONTEND_TYPED_SUFFIX,
        "resolve_geometry",
        "extract_stencils",
    )
    assert result.geometry is not None
    assert result.stencils is not None


def test_pipeline_ast_capture_callback_receives_named_stages(tmp_path):
    captured = []

    def capture(_ast, stage):
        captured.append(stage)

    compile_file(
        _write_program(tmp_path),
        PipelineProfile.CODEGEN,
        PipelineOptions(
            capture_ast=capture,
            enable_collinearity_rewrite=False,
            enable_scalar_cse=False,
            enable_slice_simplify=False,
            require_stencils=True,
        ),
    )

    assert captured == [
        "parsing",
        "symbols",
        "constants",
        "ranges",
        "types",
        "promotions",
        "constant_folding",
        "function_inlining",
        "intrinsic_arg_hoisting",
    ]


def test_build_backend_context_reuses_pipeline_results(tmp_path):
    result = compile_file(
        _write_program(tmp_path),
        PipelineProfile.CODEGEN,
        PipelineOptions(
            require_stencils=True,
            require_geometry=True,
            geometry_lint=False,
        ),
    )

    context = build_backend_context(result)

    assert context.ast is result.ast
    assert context.stencils is result.stencils
    assert context.geometry is result.geometry
    assert context.lattice_info["f"]["d"] == 1
    assert context.lattice_info["f"]["q"] == 1
