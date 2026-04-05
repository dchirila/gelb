#!/usr/bin/env python3
"""Canonical frontend + midware pipeline profiles.

The compiler has several intentional pipeline modes: code generation,
diagnostics JSON, and program-analysis viewers.  This module keeps their pass
orders explicit and gives callers one place to run them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

import gelb.utils.config
from gelb.utils.misc import load_file


class PipelineProfile(Enum):
    """Named compiler pipeline profiles."""

    CODEGEN = "codegen"
    DIAGNOSTICS = "diagnostics"
    PROGRAM_ANALYSIS = "program_analysis"


@dataclass(frozen=True)
class PipelineOptions:
    """Options that affect pipeline execution."""

    defines: tuple[str, ...] = ()
    capture_ast: Callable[[object, str], None] | None = None
    # Off by default: the collinearity rewrite re-associates and has no
    # general error bound (user manual, Numerical semantics: What the
    # optimizer promises).  It returns under ``--associative-math`` in 1.1.
    enable_collinearity_rewrite: bool = False
    enable_scalar_cse: bool = True
    enable_slice_simplify: bool = True
    require_stencils: bool = False
    require_geometry: bool = False
    emit_warnings: bool = False
    geometry_lint: bool = True
    # Strict build (user manual, Numerical semantics: Build modes): no
    # fused multiply-add in GeLB-visible arithmetic or in the runtime
    # helpers.  The passes do not change; the backends emit the switch
    # the runtime headers read, and ``gelb-run`` adds the matching
    # native flags.
    strict_fp: bool = False


@dataclass
class CompilationResult:
    """Result of running a compiler pipeline profile."""

    ast: object
    pass_names: tuple[str, ...]
    stencils: object | None = None
    geometry: object | None = None
    # (message, hint, source_line): the 1-based line a warning is about,
    # or None when it concerns no single place in the source.
    warnings: tuple[tuple[str, str, int | None], ...] = field(
        default_factory=tuple)


@dataclass(frozen=True)
class BackendContext:
    """Shared analysis facts consumed by code-generation backends."""

    ast: object
    lattice_info: dict
    stencils: object
    geometry: object


def build_backend_context(
        result: CompilationResult, *, geometry=None) -> BackendContext:
    """Build the backend-facing context from a pipeline result.

    ``geometry`` is explicit so callers can preserve their desired error
    timing.  In the CLI, output-mode validation intentionally happens before
    geometry resolution for normal codegen.
    """
    if result.stencils is None:
        raise ValueError(
            "BackendContext requires stencils; run the pipeline with "
            "require_stencils=True.")

    resolved_geometry = geometry if geometry is not None else result.geometry
    if resolved_geometry is None:
        raise ValueError(
            "BackendContext requires resolved geometry; pass geometry= or "
            "run the pipeline with require_geometry=True.")

    from gelb.midware.ast_eval import collect_lattice_info
    return BackendContext(
        ast=result.ast,
        lattice_info=collect_lattice_info(result.ast),
        stencils=result.stencils,
        geometry=resolved_geometry,
    )


def compile_file(
        input_file: str | Path,
        profile: PipelineProfile,
        options: PipelineOptions | None = None) -> CompilationResult:
    """Run a named compiler pipeline profile for ``input_file``."""
    if options is None:
        options = PipelineOptions()

    gelb.utils.config.GELB_FILE_NAME = str(input_file)
    src_raw = load_file(str(input_file))
    return compile_source(src_raw, profile, options)


def compile_source(
        src_raw: str,
        profile: PipelineProfile,
        options: PipelineOptions | None = None) -> CompilationResult:
    """Run a named compiler pipeline profile for already-loaded source."""
    if options is None:
        options = PipelineOptions()

    gelb.utils.config.GELB_SRC_RAW = src_raw
    pass_names: list[str] = []
    warnings: list[tuple[str, str, int | None]] = []

    from gelb.frontend.stage1_frontend import (
        get_ast,
        validate_ast_root_is_program,
        build_symbols_tables,
        validate_lattice_access_context,
        validate_block_signatures,
        validate_node_classes,
        initial_validation_geometry,
        validate_global_constant_initializers,
        resolve_all_constants,
        resolve_ranges,
        prevent_clashes_of_symbol_refs_with_implicits,
        prevent_clashes_of_symbol_defs_with_implicits,
        detect_function_recursion,
        add_implicit_symbols,
        validate_fixed_geometry,
        infer_types,
        promote_types,
        validate_types,
        validate_constant_assignments,
        validate_lattice_consistency,
    )
    from gelb.midware.stage2_midware import (
        validate_midware_input,
        fold_constants,
        lower_local_constants,
        validate_division_by_zero,
        validate_streaming_intrinsic_args,
        extract_stencils,
        validate_initializer_coverage,
        warn_writeonly_dynamics,
        warn_unused_lattices,
    )
    from gelb.midware.inline_functions import inline_functions

    def record(name: str) -> None:
        pass_names.append(name)

    def capture(ast, stage_name: str) -> None:
        if options.capture_ast is not None:
            options.capture_ast(ast, stage_name)

    def emit_warning(msg: str, hint: str, source_line: int | None) -> None:
        warnings.append((msg, hint, source_line))
        if options.emit_warnings:
            from gelb.utils.output_to_terminal import warning_with_hint_to_term
            warning_with_hint_to_term(msg, hint, source_line)

    ast = get_ast("gelb_program", src_raw)
    record("parse")
    capture(ast, "parsing")

    validate_ast_root_is_program(ast)
    record("validate_ast_root")

    validate_lattice_access_context(ast)
    record("validate_lattice_access_context")

    validate_block_signatures(ast)
    record("validate_block_signatures")

    prevent_clashes_of_symbol_refs_with_implicits(ast)
    record("prevent_symbol_ref_implicit_clashes")

    ast = build_symbols_tables(ast)
    record("build_symbols_tables")
    capture(ast, "symbols")

    prevent_clashes_of_symbol_defs_with_implicits(ast)
    record("prevent_symbol_def_implicit_clashes")

    if profile in (PipelineProfile.CODEGEN, PipelineProfile.DIAGNOSTICS):
        detect_function_recursion(ast)
        record("detect_function_recursion")

    ast = add_implicit_symbols(ast)
    record("add_implicit_symbols")

    validate_fixed_geometry(ast)
    record("validate_fixed_geometry")

    if options.defines:
        from gelb.frontend.constant_overrides import (
            parse_overrides, apply_constant_overrides)
        overrides = parse_overrides(options.defines)
        ast = apply_constant_overrides(ast, overrides)
        record("apply_constant_overrides")

    validate_global_constant_initializers(ast)
    record("validate_global_constant_initializers")

    ast = resolve_all_constants(ast)
    record("resolve_all_constants")
    capture(ast, "constants")

    ast = resolve_ranges(ast)
    record("resolve_ranges")
    capture(ast, "ranges")

    ast = infer_types(ast)
    record("infer_types")
    capture(ast, "types")

    ast = promote_types(ast)
    record("promote_types")
    capture(ast, "promotions")

    ast = validate_types(ast)
    record("validate_types")

    ast = validate_constant_assignments(ast)
    record("validate_constant_assignments")

    validate_lattice_consistency(ast)
    record("validate_lattice_consistency")

    validate_node_classes(ast)
    record("validate_node_classes")

    initial_validation_geometry(ast)
    record("initial_validation_geometry")

    validate_midware_input(ast)
    record("validate_midware_input")

    ast = fold_constants(ast)
    record("fold_constants")
    capture(ast, "constant_folding")

    ast = validate_division_by_zero(ast)
    record("validate_division_by_zero")

    ast = lower_local_constants(ast)
    record("lower_local_constants")

    if profile in (PipelineProfile.CODEGEN, PipelineProfile.DIAGNOSTICS):
        validate_streaming_intrinsic_args(ast)
        record("validate_streaming_intrinsic_args")

        # random() draws once per element and left to right, in every
        # build (user manual, Numerical semantics: Random numbers):
        # sequenced here, before any pass that could move an expression.
        # The inliner is one: it hoists a call's arguments ahead of the
        # statement, so it runs after the draws of the arguments and of
        # the function bodies have their temporaries.
        from gelb.midware.DrawSequencing import sequence_draws
        sequence_draws(ast)
        record("sequence_draws")

        ast = inline_functions(ast)
        record("inline_functions")
        capture(ast, "function_inlining")

        from gelb.midware.IntrinsicArgHoisting import hoist_intrinsic_args
        hoist_intrinsic_args(ast)
        record("hoist_intrinsic_args")
        capture(ast, "intrinsic_arg_hoisting")

        if options.enable_collinearity_rewrite:
            from gelb.midware.CollinearityRewriteVisitor import (
                collinearity_rewrite)
            ast = collinearity_rewrite(ast)
            record("collinearity_rewrite")
            capture(ast, "collinearity_rewrite")

        if options.enable_scalar_cse:
            from gelb.midware.ScalarBlockCSEVisitor import cse_scalar_blocks
            ast = cse_scalar_blocks(ast)
            record("scalar_block_cse")
            capture(ast, "scalar_block_cse")

        if options.enable_slice_simplify:
            from gelb.midware.SliceDFExpansionVisitor import expand_slice_dfs
            ast = expand_slice_dfs(ast)
            record("slice_df_expansion")
            capture(ast, "slice_df_expansion")

    stencil_result = None
    geometry = None

    if profile is PipelineProfile.PROGRAM_ANALYSIS:
        if options.require_geometry:
            geometry = _resolve_geometry(ast)
            record("resolve_geometry")
        if options.require_stencils:
            stencil_result = extract_stencils(ast)
            record("extract_stencils")
    elif options.require_stencils:
        stencil_result = extract_stencils(ast)
        record("extract_stencils")

        validate_initializer_coverage(stencil_result)
        record("validate_initializer_coverage")

        for msg, hint, line in warn_writeonly_dynamics(stencil_result):
            emit_warning(msg, hint, line)
        record("warn_writeonly_dynamics")

        for msg, hint, line in warn_unused_lattices(stencil_result):
            emit_warning(msg, hint, line)
        record("warn_unused_lattices")

        # Every check that needs the class map runs on the resolved
        # geometry, the one map the backends use: the wall check
        # included, since only the map shows the classes a `where`
        # predicate paints.  A caller that does not
        # resolve the geometry here (gelbc's normal codegen validates the
        # output mode first) gets the same checks, in the same order,
        # from resolve_geometry_for_compile.
        if options.require_geometry:
            geometry = _resolve_geometry(ast)
            record("resolve_geometry")
            _validate_and_lint_geometry(
                geometry,
                stencil_result,
                geometry_lint=options.geometry_lint,
                warning_sink=emit_warning,
            )
            record("validate_boundary_access")
            record("validate_write_destinations")
            record("validate_df_coverage")
            if options.geometry_lint:
                record("geometry_lint")

    return CompilationResult(
        ast=ast,
        pass_names=tuple(pass_names),
        stencils=stencil_result,
        geometry=geometry,
        warnings=tuple(warnings),
    )


def _resolve_geometry(ast):
    from gelb.midware.geometry import resolve_geometry
    return resolve_geometry(ast)


def _geometry_lint_warnings(geometry, stencil_result):
    from gelb.midware.geometry_lint import all_geometry_warnings
    return all_geometry_warnings(geometry, stencil_result)


def _validate_and_lint_geometry(
        geometry, stencil_result, *, geometry_lint, warning_sink):
    """The checks that need the resolved class map, in order: writes off
    a wall, destinations of writes at an offset, DF coverage per cell and
    phase (all hard errors), then the geometry lint (warnings).  This is
    the one path every compilation takes, whether the pipeline resolved
    the geometry itself or ``resolve_geometry_for_compile`` did."""
    from gelb.midware.stage2_midware import (
        validate_boundary_access, validate_cross_nc_df_coverage,
        validate_write_destinations)
    validate_boundary_access(stencil_result, geometry)
    validate_write_destinations(stencil_result, geometry)
    validate_cross_nc_df_coverage(stencil_result, geometry)
    if geometry_lint:
        for msg, hint, line in _geometry_lint_warnings(geometry, stencil_result):
            warning_sink(msg, hint, line)


def _resolve_geometry_with_lint(
        ast, stencil_result, *, geometry_lint, warning_sink):
    geometry = _resolve_geometry(ast)
    _validate_and_lint_geometry(
        geometry, stencil_result,
        geometry_lint=geometry_lint, warning_sink=warning_sink)
    return geometry


def resolve_geometry_for_compile(
        ast, stencil_result, *, emit_warnings=False, geometry_lint=True):
    """Resolve geometry and optionally emit geometry-lint warnings."""
    warnings: list[tuple[str, str, int | None]] = []

    def warning_sink(msg: str, hint: str, source_line: int | None) -> None:
        warnings.append((msg, hint, source_line))
        if emit_warnings:
            from gelb.utils.output_to_terminal import warning_with_hint_to_term
            warning_with_hint_to_term(msg, hint, source_line)

    geometry = _resolve_geometry_with_lint(
        ast,
        stencil_result,
        geometry_lint=geometry_lint,
        warning_sink=warning_sink,
    )
    return geometry, tuple(warnings)
