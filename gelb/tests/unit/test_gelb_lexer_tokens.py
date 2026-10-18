import importlib.util
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_docs_lexer_module():
    path = REPO_ROOT / "docs" / "_ext" / "gelb_lexer.py"
    spec = importlib.util.spec_from_file_location("gelb_docs_lexer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _alternatives(pattern):
    match = re.search(r"\(([^()]+)\)", pattern)
    assert match is not None
    return set(match.group(1).split("|"))


def _vscode_pattern(repository, group, index=0):
    return repository[group]["patterns"][index]["match"]


def test_docs_lexer_token_lists_match_vscode_grammar():
    docs_lexer = _load_docs_lexer_module()
    grammar_path = (
        REPO_ROOT / "vscode-gelb" / "syntaxes" / "gelb.tmLanguage.json")
    repository = json.loads(grammar_path.read_text())["repository"]

    assert set(docs_lexer.BLOCK_KEYWORDS) == _alternatives(
        _vscode_pattern(repository, "keywords", 0))
    assert set(docs_lexer.MODIFIER_KEYWORDS) == _alternatives(
        _vscode_pattern(repository, "keywords", 1))
    assert set(docs_lexer.RESERVED_KEYWORDS) == _alternatives(
        _vscode_pattern(repository, "keywords", 2))
    assert set(docs_lexer.TYPE_KEYWORDS) == _alternatives(
        _vscode_pattern(repository, "types"))
    assert set(docs_lexer.CONSTANT_KEYWORDS) == _alternatives(
        _vscode_pattern(repository, "constants", 0))
    assert set(docs_lexer.INTRINSIC_FUNCTIONS) == _alternatives(
        _vscode_pattern(repository, "intrinsic-functions"))
