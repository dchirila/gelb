"""Minimal Pygments lexer for GeLB source blocks.

Mirrors the classification of tokens in the VSCode extension's
TextMate grammar (vscode-gelb/syntaxes/gelb.tmLanguage.json) so
`.. code-block:: gelb` produces the same highlighting the user
sees in their editor.
"""

from __future__ import annotations

from pygments.lexer import RegexLexer, words
from pygments.token import (
    Comment,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Whitespace,
)


BLOCK_KEYWORDS = (
    "simulation_description",
    "global_constants",
    "lattices", "lattice",
    "initializer",
    "dynamic",
    "gauge",
    "node_classes", "node_class",
    "geometry",
    "nodes",
    "border",
    "where",
    "function",
    "masked",
)

# Reserved for later language stages (moving geometry); not
# implemented features, but not usable as identifiers either.
RESERVED_KEYWORDS = (
    "enter", "leave", "reduce", "reduction", "update",
    "global_variables", "transition", "zone",
)

MODIFIER_KEYWORDS = ("in", "out", "const")

TYPE_KEYWORDS = (
    "int", "int8", "int16", "int32", "int64",
    "real", "real16", "real32", "real64",
    "bool", "array",
)

CONSTANT_KEYWORDS = ("true", "false")

INTRINSIC_FUNCTIONS = (
    "sum", "dot_prod",
    "sin", "cos", "tan", "tanh",
    "sqrt", "exp", "log",
    "abs", "min", "max", "mod", "atan2",
    "random",
    "matmul", "transpose", "inverse", "determinant",
    "upstream_dfs", "bounce_back_dfs",
)


class GelbLexer(RegexLexer):
    """Pygments lexer for *.gelb files."""

    name = "GeLB"
    aliases = ["gelb"]
    filenames = ["*.gelb"]

    tokens = {
        "root": [
            # Comments first -- line and block.
            (r"//.*?$", Comment.Single),
            (r"/\*", Comment.Multiline, "blockcomment"),

            # String literals (used in simulation_description).
            (r'"([^"\\]|\\.)*"', String.Double),

            # Keywords (order matters for the longer tokens to win).
            (words(BLOCK_KEYWORDS, prefix=r"\b", suffix=r"\b"), Keyword),
            (words(RESERVED_KEYWORDS, prefix=r"\b", suffix=r"\b"), Keyword.Reserved),
            (words(MODIFIER_KEYWORDS, prefix=r"\b", suffix=r"\b"), Keyword.Declaration),
            (words(TYPE_KEYWORDS, prefix=r"\b", suffix=r"\b"), Keyword.Type),
            (words(CONSTANT_KEYWORDS, prefix=r"\b", suffix=r"\b"), Keyword.Constant),
            (words(INTRINSIC_FUNCTIONS, prefix=r"\b", suffix=r"\b"), Name.Builtin),

            # Implicit lattice-coordinate variables.
            (r"\b[xyz]\b", Name.Builtin.Pseudo),

            # Numeric literals.
            (r"\d+\.\d+([eE][+-]?\d+)?", Number.Float),
            (r"\d+", Number.Integer),

            # Operators and punctuation.
            (r"==|!=|<=|>=|&&|\|\||[+\-*/%^=<>!]", Operator),
            (r"[{}()\[\],;:.|]", Punctuation),

            # User identifiers.
            (r"[A-Za-z_][A-Za-z0-9_]*", Name),

            # Whitespace.
            (r"\s+", Whitespace),
        ],
        "blockcomment": [
            (r"[^*/]+", Comment.Multiline),
            (r"/\*", Comment.Multiline, "#push"),
            (r"\*/", Comment.Multiline, "#pop"),
            (r"[*/]", Comment.Multiline),
        ],
    }
