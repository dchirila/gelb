"""Diagnostics expectations for public examples and hardening fixtures."""

from __future__ import annotations

import json
import pathlib

from click.testing import CliRunner

from gelb.gelbc import cli as gelbc_cli


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_EXAMPLES_DIR = _REPO_ROOT / "examples"
_HARDENING_DIR = _REPO_ROOT / "gelb/tests/fixtures/hardening"


def _run_diagnostics_path(path: pathlib.Path):
    result = CliRunner().invoke(
        gelbc_cli,
        [str(path), "--diagnostics-json"],
    )
    payload = json.loads(result.output)
    return result.exit_code, payload["diagnostics"]


def _run_diagnostics(rel_path: str):
    return _run_diagnostics_path(_REPO_ROOT / rel_path)


def _line_of(path: pathlib.Path, text: str) -> int:
    """1-based number of the first line of ``path`` that contains ``text``."""
    return next(i for i, line in enumerate(path.read_text().splitlines(), 1)
                if text in line)


def _public_examples():
    return sorted(_EXAMPLES_DIR.rglob("*.gelb"))


def test_public_examples_have_clean_diagnostics():
    failures = []
    for example in _public_examples():
        code, diagnostics = _run_diagnostics_path(example)
        errors = [d for d in diagnostics if d["severity"] == "error"]
        if code != 0 or errors:
            rel = example.relative_to(_REPO_ROOT)
            messages = "; ".join(d["message"] for d in errors)
            failures.append(f"{rel}: {messages}")

    assert not failures


def test_hardening_discontinuous_periodic_geometry_fails():
    code, diagnostics = _run_diagnostics_path(
        _HARDENING_DIR / "discontinuous_periodic_geometry.gelb"
    )

    assert code == 1
    assert any(
        d["severity"] == "error"
        and "declared periodic" in d["message"]
        and "wrap-partner" in d["message"]
        for d in diagnostics
    )


def test_hardening_unused_lattice_warns_only():
    code, diagnostics = _run_diagnostics_path(
        _HARDENING_DIR / "unused_lattice.gelb"
    )

    assert code == 0
    assert any(
        d["severity"] == "warning"
        and "declared but never read or written" in d["message"]
        for d in diagnostics
    )


def test_warning_points_at_its_block():
    """A warning's range is the line that opens the block it is about,
    so the Problems panel jumps there rather than to the top of the
    file."""
    path = _EXAMPLES_DIR / "basic/1d/ex0_int_vec_setto_one.gelb"
    code, diagnostics = _run_diagnostics_path(path)
    assert code == 0
    [warning] = [d for d in diagnostics if "never reads f.in" in d["message"]]
    line = _line_of(path, "dynamic SetDFsToOne") - 1      # 0-based
    assert warning["range"] == {"startLine": line, "startCol": 0,
                                "endLine": line,
                                "endCol": len("dynamic SetDFsToOne { //")}


def test_unused_lattice_warning_points_at_its_declaration():
    path = _HARDENING_DIR / "unused_lattice.gelb"
    code, diagnostics = _run_diagnostics_path(path)
    [warning] = [d for d in diagnostics
                 if "declared but never read" in d["message"]]
    assert warning["range"]["startLine"] == _line_of(path, "lattice g(") - 1
    assert warning["range"]["startCol"] == 2        # after the indentation


def test_unsupported_lattice_index_is_an_error_on_its_line(tmp_path):
    """An index that is not the axis coordinate plus a constant is
    reported where it is, instead of being taken as offset 0."""
    source = (
        'simulation_description("index test");\n'
        'lattices { lattice u(1, 1, real, 8, true); }\n'
        'initializer I { u.out[x | 0] = x; }\n'
        'dynamic D { u.out[x | 0] = u.in[2 * x | 0]; }\n'
        'gauge G -> (real v) { v = u.in[x | 0]; }\n'
        'node_classes { node_class B(I, D, G); }\n'
        'geometry { nodes[:] = B; }\n'
    )
    path = tmp_path / "index.gelb"
    path.write_text(source)
    code, diagnostics = _run_diagnostics_path(path)
    assert code == 1
    [error] = [d for d in diagnostics if d["severity"] == "error"]
    assert "along x with '2 * x'" in error["message"]
    assert error["range"]["startLine"] == 3          # 0-based: line 4
