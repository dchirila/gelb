"""Shared frontend+midware pipeline for program-analysis viewers.

Both ``algo_viewer.compile_to_stencils()`` and
``geo_viewer.compile_to_geometry()`` ran identical frontend+midware
passes.  This module consolidates the pipeline into one function so
both can share it (and the unified ``gelb-view source`` subcommand
can run it once and extract both views).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

from gelb.midware.geometry import ResolvedGeometry
from gelb.midware.stencil import ProgramStencils


@dataclass
class ProgramAnalysis:
    """Complete compile-time analysis of a GeLB program.

    Bundles the resolved geometry and the program stencils -- everything
    needed to render any of the `gelb-view source` modes (geometry,
    stencils, side-by-side, combined-overlay).
    """
    geometry: ResolvedGeometry
    stencils: ProgramStencils


def run_analysis_pipeline(gelb_file: str | pathlib.Path):
    """Run frontend + midware passes and return the typed AST.

    This is the shared part of `compile_to_stencils()` and
    `compile_to_geometry()` -- useful when only one of the two outputs
    is needed.
    """
    from gelb.compiler_pipeline import (
        PipelineProfile, PipelineOptions, compile_file)

    result = compile_file(
        gelb_file,
        PipelineProfile.PROGRAM_ANALYSIS,
        PipelineOptions(),
    )
    return result.ast


def compile_to_program_analysis(
        gelb_file: str | pathlib.Path) -> ProgramAnalysis:
    """Compile a GeLB file and return both geometry and stencils.

    Runs the shared frontend+midware pipeline once, then extracts:
      - the resolved per-cell node-class map (`ResolvedGeometry`)
      - the per-block I/O stencils (`ProgramStencils`)

    Both outputs are needed for the unified `gelb-view source` viewer
    and for the combined-overlay render.
    """
    from gelb.compiler_pipeline import (
        PipelineProfile, PipelineOptions, compile_file)

    result = compile_file(
        gelb_file,
        PipelineProfile.PROGRAM_ANALYSIS,
        PipelineOptions(require_geometry=True, require_stencils=True),
    )
    return ProgramAnalysis(geometry=result.geometry, stencils=result.stencils)
