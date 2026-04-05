"""The parser regeneration must never leave the tree without a parser;
the helper once deleted the live parser before the tool ran.
``invoke_antlr4_tool`` runs whenever a process
fails to import the generated files, so a failed tool run, or a process
that observed the files missing while another regenerated them, must
not delete them for everyone else: the tool writes into a scratch
directory and the results replace the live files only on success."""

import subprocess

import pytest

from gelb.utils import misc
from gelb.utils.exceptions import GeLBExAntlr4JavaToolFailed

_GENERATED = ("GeLBLexer.py", "GeLBParser.py", "GeLBVisitor.py")


@pytest.fixture
def generated_dir(tmp_path, monkeypatch):
    """A fake package layout the helper resolves its paths from."""
    package = tmp_path / "gelb"
    grammars = package / "antlr_part" / "grammars"
    output = package / "antlr_part" / "generated_code"
    grammars.mkdir(parents=True)
    output.mkdir(parents=True)
    (grammars / "GeLB.g4").write_text("grammar GeLB;\n")
    for name in _GENERATED:
        (output / name).write_text(f"# live {name}\n")
    monkeypatch.setattr(misc, "__file__", str(package / "utils" / "misc.py"))
    monkeypatch.setattr(misc, "ensure_python3_package_is_present", lambda _name: None)
    monkeypatch.setattr(misc, "initialize_reserved_keywords", lambda: None)
    return output


def test_a_failed_tool_run_leaves_the_generated_files_in_place(generated_dir, monkeypatch):
    def failing_tool(args, **_kwargs):
        return subprocess.CompletedProcess(args, 1, "", "Unable to locate a Java Runtime.")

    monkeypatch.setattr(misc, "run", failing_tool)
    with pytest.raises(GeLBExAntlr4JavaToolFailed):
        misc.invoke_antlr4_tool()
    for name in _GENERATED:
        assert (generated_dir / name).read_text() == f"# live {name}\n"
    assert not list(generated_dir.glob(".antlr4_tmp_*"))


def test_a_successful_run_replaces_the_files_only_from_its_own_output(generated_dir, monkeypatch):
    def writing_tool(args, cwd, **_kwargs):
        scratch = misc.pathlib.Path(cwd) / args[args.index("-o") + 1]
        assert scratch.name.startswith(".antlr4_tmp_"), "the tool writes into a scratch directory"
        for name in _GENERATED:
            (scratch / name).write_text(f"# new {name}\n")
        (scratch / "GeLB.tokens").write_text("T=1\n")
        # The live files are untouched while the tool runs.
        for name in _GENERATED:
            assert (generated_dir / name).read_text() == f"# live {name}\n"
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(misc, "run", writing_tool)
    misc.invoke_antlr4_tool()
    for name in _GENERATED:
        assert (generated_dir / name).read_text() == f"# new {name}\n"
    assert (generated_dir / "GeLB.tokens").exists()
    assert not list(generated_dir.glob(".antlr4_tmp_*"))
