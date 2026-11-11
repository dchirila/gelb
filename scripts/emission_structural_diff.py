#!/usr/bin/env python3
"""Compare emitted tokens, allowing only bijective renaming of temporaries.

Usage: emission_structural_diff.py BASELINE CANDIDATE
Inputs are source files or directories with identical relative file sets.
Whitespace and comments are ignored; literal spelling and token order are not.
"""

import argparse
from pathlib import Path
import re

TEMP_RE = re.compile(
    r"^(?:gelb_b\d+_)?g_(?:__+[A-Za-z0-9_]+?_\d+_[A-Za-z0-9_]+"
    r"|_+gelb_+(?:draw|call|dpa|pre_+cse|cse)_+\d+[A-Za-z0-9_]*"
    r"|gelb_(?:tmp|matmul_in)_[A-Za-z0-9_]+)$|^gelb_tmp_[A-Za-z0-9_]+$")
STRINGS = r'''"(?:\\.|""|[^"\\])*"|'(?:\\.|''|[^'\\])*' '''.strip()
WORDS = (r"(?:0[xX][0-9a-fA-F]+(?:\.[0-9a-fA-F]*)?(?:[pP][+-]?\d+)?"
         r"|(?:\d+\.\d*|\.\d+|\d+)(?:[eEdD][+-]?\d+)?)[A-Za-z0-9_]*"
         r"|[A-Za-z_][A-Za-z0-9_]*|\.\w+\."
         r"|<<=|>>=|::|->|\*\*|//|&&|\|\||==|!=|<=|>=|\+\+|--|"
         r"\+=|-=|\*=|/=|<<|>>|\S")


def tokens(text, fortran=False):
    comments = r"![^\n]*" if fortran else r"//[^\n]*|/\*[\s\S]*?\*/"
    strings = STRINGS if fortran else r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*' '''.strip()
    lexer = re.compile(f"(?P<string>{strings})|(?P<comment>{comments})|(?P<token>{WORDS})")
    return [m.group() for m in lexer.finditer(text) if m.lastgroup != "comment"]


def fortran_lines(text):
    """Join free-form continuations without changing token or string boundaries."""
    parts, quote = [], None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("!"):
            continue
        if parts:
            if line.lstrip().startswith("&"):
                line = line.lstrip()[1:]
            elif quote:
                raise ValueError("continued character literal needs a leading ampersand")
        i = 0
        while i < len(line):
            char = line[i]
            if quote:
                if char == "\\":
                    i += 2
                    continue
                if char == quote:
                    if i + 1 < len(line) and line[i + 1] == quote:
                        i += 2
                        continue
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == "!":
                break
            i += 1
        code = line[:i].rstrip()
        if code.endswith("&"):
            # Keep spaces before '&': 'not &\n&x' differs from 'not&\n&x'.
            parts.append(code[:-1])
        else:
            if quote:
                raise ValueError("unterminated Fortran character literal")
            yield "".join([*parts, code])
            parts = []
    if parts:
        raise ValueError("unterminated Fortran continuation")


def canonical_tokens(text, suffix):
    """Preserve tokens and temporary bindings in routines and C-family blocks."""
    output, names = [], {}

    def append(token):
        if TEMP_RE.fullmatch(token):
            output.append(("temporary", names.setdefault(token, len(names))))
        else:
            output.append(("token", token))

    if suffix.lower() == ".f90":
        stack = []
        start = re.compile(r"^\s*(?:(?!end\b)\w+(?:\([^)]*\))?\s+)*"
                           r"(?:program|subroutine|function)\s+\w+", re.I)
        end = re.compile(r"^\s*end\s*(?:program|subroutine|function)\b", re.I)
        for line in fortran_lines(text):
            if start.match(line):
                stack.append(names)
                names = {}
            for token in tokens(line, fortran=True):
                append(token)
            if end.match(line):
                if not stack:
                    raise ValueError("unmatched Fortran routine end")
                names = stack.pop()
        if stack:
            raise ValueError("unterminated Fortran routine")
    else:
        stack = []
        for token in tokens(text):
            if token == "{":
                stack.append(names)
                # Inner loops still see enclosing temporaries. New names expire
                # at this brace, so sibling blocks may reuse their spellings.
                names = dict(names)
            append(token)
            if token == "}":
                if not stack:
                    raise ValueError("unmatched closing brace")
                names = stack.pop()
        if stack:
            raise ValueError("unterminated brace")
    return output


def equivalent(before, after, suffix):
    return canonical_tokens(before, suffix) == canonical_tokens(after, suffix)


def sources(path):
    if path.is_file():
        return {"source": path}
    return {str(p.relative_to(path)): p for p in path.rglob("*")
            if p.is_file() and p.suffix in (".cpp", ".cu", ".f90")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    before, after = sources(args.baseline), sources(args.candidate)
    if not before or before.keys() != after.keys():
        print("FAIL: empty or different source-file sets", sorted(before.keys() ^ after.keys()))
        return 1
    bad = 0
    for name, path in before.items():
        try:
            same = path.suffix == after[name].suffix and equivalent(path.read_text(), after[name].read_text(), path.suffix)
        except ValueError as error:
            print(f"{name}: {error}")
            same = False
        if not same:
            print(f"STRUCTURAL DIFF: {name}")
            bad += 1
    print(f"structural comparison: {len(before) - bad} identical, {bad} different")
    return int(bad != 0)


if __name__ == "__main__":
    raise SystemExit(main())
