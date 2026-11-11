"""Every integration file belongs to exactly one CI shard or local exemption."""

import ast
from collections import Counter
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[3]
LOCAL_GATE_ONLY = ("test_examples_smoke.py", "test_plain_build_compiles.py", "test_reproducibility.py")
EMPTY_PLACEHOLDERS = ("test_frontend.py",)


def ci_files(workflow):
    """Read active paths scalars; shell comments in a folded scalar are unsafe."""
    paths, block_indent = [], None
    for line in workflow.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if block_indent is not None and indent <= block_indent:
            block_indent = None
        entry = re.fullmatch(r"\s+paths:\s*(.*)", line)
        if entry:
            value = entry[1]
            if value == ">-":
                block_indent = indent
                continue
        elif block_indent is not None:
            value = line.strip()
        else:
            continue
        assert "#" not in value, "shell comment in a paths scalar"
        assert re.fullmatch(r"gelb/tests/(?:unit|numeric|integration/test_\w+\.py)", value), value
        if value.startswith("gelb/tests/integration/"):
            paths.append(value.rsplit("/", 1)[1])
    return paths


def test_integration_partition():
    directory = ROOT / "gelb/tests/integration"
    workflow = (ROOT / ".github/workflows/release-health.yml").read_text()
    ci = ci_files(workflow)
    counts = Counter([*ci, *LOCAL_GATE_ONLY, *EMPTY_PLACEHOLDERS])
    assert set(counts) == {path.name for path in directory.glob("test_*.py")}
    assert all(count == 1 for count in counts.values()), counts
    for name in EMPTY_PLACEHOLDERS:
        tree = ast.parse((directory / name).read_text())
        assert not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and node.name.startswith("test_") for node in ast.walk(tree))


@pytest.mark.parametrize("mutation", ("control", "delete", "comment_path", "comment_shard", "inline_comment", "duplicate"))
def test_partition_workflow_mutations(tmp_path, monkeypatch, mutation):
    workflow = (ROOT / ".github/workflows/release-health.yml").read_text()
    line = "              gelb/tests/integration/test_simd_vector_body.py\n"
    assert line in workflow
    if mutation == "delete":
        workflow = workflow.replace(line, "")
    elif mutation == "comment_path":
        workflow = workflow.replace(line, line.replace("gelb/", "# gelb/"))
    elif mutation == "comment_shard":
        start = workflow.index("          - name: widths-and-math")
        end = workflow.index("          - name: diagnostics", start)
        workflow = workflow[:start] + "".join("# " + s for s in workflow[start:end].splitlines(keepends=True)) + workflow[end:]
    elif mutation == "inline_comment":
        workflow = workflow.replace(line, line.rstrip() + " # disabled\n")
    elif mutation == "duplicate":
        workflow = workflow.replace(line, line + "              gelb/tests/integration/test_midware.py\n")
    directory = tmp_path / "gelb/tests/integration"
    directory.mkdir(parents=True)
    for path in (ROOT / "gelb/tests/integration").glob("test_*.py"):
        (directory / path.name).write_text(path.read_text() if path.name in EMPTY_PLACEHOLDERS else "")
    target = tmp_path / ".github/workflows/release-health.yml"
    target.parent.mkdir(parents=True)
    target.write_text(workflow)
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    if mutation == "control":
        test_integration_partition()
    else:
        with pytest.raises(AssertionError):
            test_integration_partition()
