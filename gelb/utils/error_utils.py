#!/usr/bin/env python3

import click
from colorama import Fore, Style

from gelb.utils import config


feedback_on_slack_hint = (
    f"If you are a GeLB user, please report this as a GitHub"
    f" discussion at https://github.com/dchirila/gelb/discussions"
    f" or as an issue at https://github.com/dchirila/gelb/issues."
)

learning_gelb_hint = (
    f"Please visit https://gelb-lang.org to learn more about the GeLB "
    f"programming language and about writing GeLB programs."
)


def iterate_over_lines_in_src():
    yield from enumerate(config.GELB_SRC_RAW.splitlines(), 1)


def count_lines_in_program():
    return len(config.GELB_SRC_RAW.splitlines())


def source_anchor_column(line, annotation=""):
    """Locate the name in a block/declaration or paint with only a line anchor."""
    import re

    lines = config.GELB_SRC_RAW.splitlines()
    if not 1 <= line <= len(lines):
        return 0
    text = lines[line - 1]
    matches = list(re.finditer(
        r"\b(?:initializer|dynamic|gauge|function|node_class|lattice)\s+(\w+)",
        text,
    ))
    matches.extend(re.finditer(r"\bnodes\[[^;]*?\]\s*=\s*(\w+)", text))
    # Several declarations/paints may share a source line. Prefer the
    # named subject of the diagnostic over the first declaration there.
    for name in re.findall(r"'([^']+)'", annotation):
        for match in matches:
            if match.group(1) == name:
                return match.start(1)
    return matches[0].start(1) if matches else len(text) - len(text.lstrip())


def show_source_with_annotation(line, column, click_color,
                                annotation, hint=None, *,
                                label="Problem", err=False):
    """Render source, a standalone caret, then the diagnostic and hint.

    Use the same stream for the entire excerpt (stderr for warnings).
    Diagnostics without a source location use the banner-only helpers.
    """
    lines_in_file = count_lines_in_program()
    if not 1 <= line <= lines_in_file:
        # A caller may have a location but no source text (e.g. a tool
        # displaying a previously collected finding). Never lose its message.
        click.echo(click_color + f"[{label}] {annotation}" +
                   Style.RESET_ALL, err=err)
        if hint:
            click.echo(Fore.GREEN + f"[Hint] {hint}" + Style.RESET_ALL, err=err)
        return
    click.echo(err=err)
    if line > (config.GELB_ERROR_CONTEXT + 1):
        click.echo(' ' * 6 + Fore.BLUE + '...' + Style.RESET_ALL, err=err)
    for lineno, line_text in iterate_over_lines_in_src():
        if abs(lineno - line) <= config.GELB_ERROR_CONTEXT:
            if lineno == line:
                click.echo(
                    click_color + f"{lineno:>4}->{line_text}" + Style.RESET_ALL,
                    err=err,
                )
                click.echo(' ' * (column + 6) + click_color + "^^" +
                           Style.RESET_ALL, err=err)
                click.echo(click_color + f"[{label}] {annotation}" +
                           Style.RESET_ALL, err=err)
                if hint:
                    click.echo(Fore.GREEN + f"[Hint] {hint}" +
                               Style.RESET_ALL, err=err)
            else:
                click.echo(Fore.BLUE + f"{lineno:>4}  {line_text}".rstrip() +
                           Style.RESET_ALL, err=err)
    if (lines_in_file - line) > config.GELB_ERROR_CONTEXT:
        click.echo(' ' * 6 + Fore.BLUE + '...' + Style.RESET_ALL, err=err)


def show_error_in_src(line, column, error, hint):
    show_source_with_annotation(line, column, Fore.RED, error, hint)


# --- machine-readable location extraction ---------------------------------
# Used by gelbc --diagnostics-json to convert a raised GeLBException into a
# (start_line, start_col, end_line, end_col) tuple that the VSCode extension
# can feed straight into vscode.Range. Source-file line numbers from ANTLR /
# our CodeRange class are 1-based; columns are 0-based, with `stop_col`
# pointing at the LAST character of the token (inclusive). We keep the
# 1-based line numbers here (the extension subtracts 1 itself) but make
# end_col exclusive, so a 1-character token has end_col = start_col + 1.

def _code_range_from_obj(obj):
    """Walk common "has a location" shapes. Returns a CodeRange-like object
    with .start_line / .start_col / .stop_line / .stop_col, or None."""
    if obj is None:
        return None
    if hasattr(obj, 'code_range') and obj.code_range is not None:
        return obj.code_range
    value = getattr(obj, 'value', None)
    if value is not None and hasattr(value, 'code_range') \
            and value.code_range is not None:
        return value.code_range
    return None


def resolve_error_location(ex):
    """Return (start_line, start_col, end_line, end_col) for a GeLBException
    subclass, or None if no location can be recovered.

    Lines are 1-based (matches the existing ``show_error_in_src`` API).
    ``end_col`` is exclusive (= last character's column + 1), which is what
    VSCode expects for Range.
    """
    # GeLBExSyntaxError / GeLBExInvalidNoOfOccurrences: direct fields.
    line = getattr(ex, 'line', None)
    col = getattr(ex, 'column', None)
    if line is not None and col is not None:
        return (line, col, line, col + 1)

    # GeLBExStencilError and similar block-level errors point at a
    # range of source lines rather than one token -- the VSCode
    # extension still gets a clickable row that jumps to the first
    # line of the block; the CLI path anchors at the block name.
    source_line = getattr(ex, 'source_line', None)
    if source_line is not None:
        end_line = getattr(ex, 'source_end_line', None) or source_line
        # We don't have column info, so span the whole first line from
        # column 0 to column 1 (a 1-character placeholder). VSCode's
        # Problems panel navigates by line, not column, so this is fine.
        return (source_line, 0, end_line, 1)

    # Exceptions that point at an AST node (directly or via a symbol).
    for attr in ('symbol_ref', 'identifier_node', 'node', 'call_node',
                 'curr_instance'):
        cr = _code_range_from_obj(getattr(ex, attr, None))
        if cr is None:
            continue
        start_line = cr.start_line
        start_col = cr.start_col
        end_line = cr.stop_line if cr.stop_line is not None else start_line
        end_col = (cr.stop_col + 1
                   if cr.stop_col is not None else start_col + 1)
        if end_line == start_line and end_col <= start_col:
            end_col = start_col + 1
        return (start_line, start_col, end_line, end_col)
    return None


def show_source_range(start_line, end_line, click_color=Fore.BLUE):
    """Print a range of source lines (inclusive) without annotation."""
    for (lineno, line_text) in iterate_over_lines_in_src():
        if start_line <= lineno <= end_line:
            click.echo(
                click_color + f"{lineno:>4}  {line_text}" + Style.RESET_ALL
            )


def show_double_definition_error(
        curr_line,
        curr_column,
        prev_line,
        prev_column,
        symbol_name, symbol_tag, error=None, hint=None):
    show_source_with_annotation(
        prev_line,
        prev_column,
        Fore.BLUE,
        f"Previous definiton of"
        f" "
        f"{click.style(symbol_name, underline=True) + Fore.BLUE}"
        f" (as {symbol_tag}) here."
    )
    show_source_with_annotation(
        curr_line,
        curr_column,
        Fore.RED,
        (f"Re-definition of "
         f"{click.style(symbol_name, underline=True) + Fore.RED} here."
         + (f"\n{error}" if error else "")),
        hint,
    )
