"""Post-processing formatter for Fortran free-form source code.

Ensures every line respects the 132-character limit by splitting long lines
at token boundaries.  The formatter is Fortran-aware: it never breaks number
literals (including exponent signs like ``1.5d-10``), string literals,
identifiers, or multi-character operators.

Usage::

    from gelb.backends.fortran.line_formatter import format_fortran_lines

    formatted = format_fortran_lines(raw_fortran_code)
"""

import re

__all__ = ['format_fortran_lines']

# ---------------------------------------------------------------------------
# Fortran tokenizer (regex-based)
# ---------------------------------------------------------------------------
# Ordered longest-match-first so that e.g. ``1.5d-10`` is consumed as a
# single real-with-exponent token rather than ``1.5d`` + ``-`` + ``10``.

_FORTRAN_TOKEN_RE = re.compile(r"""
    '[^']*(?:''[^']*)*'                   # single-quoted string
  | "[^"]*(?:""[^"]*)*"                   # double-quoted string
  | \.\w+\.                                # dot-operator: .and. .true. etc.
  | \d+\.?\d*[dDeE][+-]?\d+(?:_\w+)?      # real with exponent: 1.5d-10
  | \d+\.\d*(?:_\w+)?                     # real w/o exponent: 1.5, 1.0_dp
  | \.\d+(?:[dDeE][+-]?\d+)?(?:_\w+)?     # real starting with dot: .5d0
  | \d+(?:_\w+)?                           # integer with optional kind: 42_8
  | [a-zA-Z_]\w*                           # identifier / keyword
  | \*\*                                   # power
  | //                                     # concatenation
  | /=|<=|>=|==|=>                         # two-char operators
  | ::                                     # declaration separator
  | \(/                                    # array constructor open
  | /\)                                    # array constructor close
  | \s+                                    # whitespace (preserved)
  | .                                      # any other single character
""", re.VERBOSE)

# Split-point priority -- higher is better.
_SCORE_COMMA = 100
_SCORE_EQUALS = 90
_SCORE_DOUBLE_COLON = 85
_SCORE_CLOSE_PAREN = 80
_SCORE_OPERATOR = 70
_SCORE_OPEN_PAREN = 60
_SCORE_WHITESPACE = 50
_SCORE_FALLBACK = 10

_OPERATORS = frozenset({'+', '-', '*', '/'})
_CLOSE_PARENS = frozenset({')', '/)'})


def _tokenize(line):
    """Return a list of token strings whose concatenation equals *line*."""
    return _FORTRAN_TOKEN_RE.findall(line)


def _score_after(token):
    """Score a split point that occurs *after* the given token."""
    if token == ',':
        return _SCORE_COMMA
    if token == '=' or token == '=>':
        return _SCORE_EQUALS
    if token == '::':
        return _SCORE_DOUBLE_COLON
    if token in _CLOSE_PARENS:
        return _SCORE_CLOSE_PAREN
    if token in _OPERATORS:
        return _SCORE_OPERATOR
    if token.isspace():
        return _SCORE_WHITESPACE
    return _SCORE_FALLBACK


def _score_before(token):
    """Score a split point that occurs *before* the given token."""
    if token == '(' or token == '(/':
        return _SCORE_OPEN_PAREN
    return _SCORE_FALLBACK


# ---------------------------------------------------------------------------
# Continuation joining
# ---------------------------------------------------------------------------

def _is_omp_directive(line):
    """Return True if *line* is an OpenMP sentinel (``!$omp``)."""
    return line.lstrip().lower().startswith('!$omp')


def _join_continuations(lines):
    """Join physical continuation lines back into logical lines.

    A physical line ending with ``&`` (ignoring trailing whitespace) is
    continued on the next physical line.  If the continuation line starts
    with ``&`` (ignoring leading whitespace), text resumes right after
    that ``&``; otherwise it resumes at the first non-blank character.

    OpenMP directives (``!$omp ... &`` / ``!$omp& ...``) use their own
    continuation syntax and are passed through unchanged.
    """
    logical = []
    buf = None          # accumulator for the current logical line
    for raw in lines:
        rstripped = raw.rstrip()

        # OpenMP directives have their own continuation syntax --
        # do not merge them with surrounding lines.
        if _is_omp_directive(raw):
            if buf is not None:
                logical.append(buf)
                buf = None
            logical.append(raw)
            continue

        if buf is not None:
            # We are continuing a previous line.
            lstripped = raw.lstrip()
            if lstripped.startswith('&'):
                buf += lstripped[1:]        # skip the leading &
            else:
                buf += lstripped
        else:
            buf = raw                       # preserve original (incl. spaces)

        if rstripped.endswith('&'):
            buf = buf.rstrip()[:-1]         # strip trailing & (and whitespace)
        else:
            logical.append(buf)
            buf = None
    if buf is not None:
        logical.append(buf)                 # unterminated continuation
    return logical


# ---------------------------------------------------------------------------
# Line splitter
# ---------------------------------------------------------------------------

def _leading_indent(line):
    """Return the number of leading space characters in *line*."""
    return len(line) - len(line.lstrip(' '))


def _split_line(line, max_len):
    """Split one logical *line* into physical lines of <= *max_len* chars.

    Returns a list of strings (without trailing newlines).
    """
    if len(line) <= max_len:
        return [line]

    # Continuation indent is fixed for all continuation lines of this
    # logical line -- based on the *original* indent, not the current
    # fragment.  This prevents unbounded indent growth.
    indent = _leading_indent(line)
    cont_indent = indent + 4
    cont_prefix = ' ' * cont_indent + '&'

    result = []
    remaining = line
    while len(remaining) > max_len:
        tokens = _tokenize(remaining)
        if not tokens:
            result.append(remaining)
            remaining = ''
            break

        # Build cumulative column positions for each token boundary.
        col = 0
        positions = []
        for tok in tokens:
            col += len(tok)
            positions.append(col)

        # Find the best split point.
        usable = max_len - 2       # room for ' &'
        best_idx = -1
        best_score = -1
        for i in range(len(tokens) - 1):
            if positions[i] > usable:
                break
            score = max(_score_after(tokens[i]),
                        _score_before(tokens[i + 1]))
            if score >= best_score:
                best_score = score
                best_idx = i

        # Check whether the proposed split makes progress.  If the
        # non-whitespace content before the split is empty, we'd just
        # be peeling off the continuation prefix -- leading to an
        # infinite loop.  Fall back to force-split in that case.
        use_force = (best_idx < 0)
        if not use_force:
            first_part = ''.join(tokens[:best_idx + 1]).rstrip()
            if not first_part:
                use_force = True

        if use_force:
            # Force split at usable limit.
            result.append(remaining[:usable] + ' &')
            remaining = cont_prefix + remaining[usable:].lstrip()
            continue

        rest_part = ''.join(tokens[best_idx + 1:]).lstrip()
        result.append(first_part + ' &')
        remaining = cont_prefix + rest_part

    if remaining:
        result.append(remaining)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_fortran_lines(code, max_len=132):
    """Format Fortran free-form source to respect the line-length limit.

    Long lines are split at token boundaries using ``&`` continuation.
    Existing continuations are re-joined first, then re-split cleanly.
    Comment lines and short lines pass through unchanged.

    Parameters
    ----------
    code : str
        Complete Fortran source code.
    max_len : int, optional
        Maximum allowed line length (default 132 for free-form Fortran).

    Returns
    -------
    str
        Reformatted source code with all lines <= *max_len*.
    """
    physical = code.split('\n')
    logical = _join_continuations(physical)

    result = []
    for line in logical:
        stripped = line.lstrip()
        # Pass through empty / blank lines and comments.
        if stripped == '' or stripped.startswith('!'):
            result.append(line)
            continue
        result.extend(_split_line(line, max_len))

    return '\n'.join(result)
