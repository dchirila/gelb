#!/usr/bin/env python3

import click
from colorama import Fore, Style
import gelb.utils.config

GELB_KEYWORDS = [
    'array',
    'bool',
    'const',
    'dot_product',
    'down_stream_df',
    'dynamic',
    'dynamics',
    'gauge',
    'gauges',
    'geometry',
    'global_constants',
    'in',
    'initializer',
    'initializers',
    'int',
    'int16',
    'int32',
    'int64',
    'int8',
    'lattice',
    'lattices',
    'node_class',
    'node_classes',
    'nodes',
    'opposite_df',
    'out',
    'periodicity',
    'real',
    'real16',
    'real32',
    'real64',
    'simulation_description',
    'simulation_name',
    'size',
    'up_stream_df',
    'vector_product'
]

feedback_on_slack_hint = (
    f"If you are a GeLB user, please report this error on our"
    f" Slack #feedback channel (https://gelb-devs.slack.com)."
)

learning_gelb_hint = (
    f"Please visit https://gelb-lang.org to learn how to write your first "
    f"GeLB programs."
)


def iterate_over_lines_in_src():
    # iterate over lines in GELB_SRC_RAW
    current_lineno = 1
    previous_nl = -1
    while True:
        next_nl = gelb.utils.config.GELB_SRC_RAW.find('\n', previous_nl + 1)
        if next_nl < 0:
            break
        yield (current_lineno,
               gelb.utils.config.GELB_SRC_RAW[(previous_nl + 1): next_nl])
        previous_nl = next_nl
        current_lineno += 1


def count_lines_in_program():
    no_lines = 0
    for (lineno, line_text) in iterate_over_lines_in_src():
        no_lines += 1
    return no_lines


def show_double_definition_error(
        curr_line,
        curr_column,
        prev_line,
        prev_column,
        symbol_name, symbol_type):
    lines_in_file = count_lines_in_program()

    click.echo()  # newline
    # print previous definition
    # print top gutter (..., if lines of context are not near the start)
    if prev_line > (gelb.utils.config.GELB_ERROR_CONTEXT + 1):
        click.echo(' ' * 6 + Fore.BLUE + '...' + Style.RESET_ALL)
    # iterate over all lines in the file
    for (lineno, line_text) in iterate_over_lines_in_src():
        # check whether problematic line is part of the context we want
        # to show (i.e. a few lines before & after problematic line)
        if (abs(lineno - prev_line) <= gelb.utils.config.GELB_ERROR_CONTEXT):
            # print each of the selected lines of context
            if lineno == prev_line:
                # special treatment for the problematic line
                line_width = len(line_text)
                click.echo(
                    Fore.BLUE + f"{lineno:>4}->{line_text}" +
                    Style.RESET_ALL
                )

                click.echo(' ' * (prev_column + 6), nl=False)
                click.echo(
                    Fore.BLUE + ("^^" + (" " * (line_width - 1))) + (
                            f"[Problem] Previous definition of \""
                            f"{symbol_name}\" (as a {symbol_type}) here."
                    ) +
                    Style.RESET_ALL
                )
            else:
                # normal print, for non-problematic line
                click.echo(
                    Fore.BLUE + f"{lineno:>4}  {line_text}" + Style.RESET_ALL
                )
    # print bottom gutter (..., if lines of context are not near the end)
    if (lines_in_file - prev_line) > gelb.utils.config.GELB_ERROR_CONTEXT:
        click.echo(' ' * 6 + Fore.BLUE + '...' + Style.RESET_ALL)

    click.echo()  # newline
    # print current definition
    # print top gutter (..., if lines of context are not near the start)
    if curr_line > (gelb.utils.config.GELB_ERROR_CONTEXT + 1):
        click.echo(' ' * 6 + Fore.BLUE + '...' + Style.RESET_ALL)
    # iterate over all lines in the file
    for (lineno, line_text) in iterate_over_lines_in_src():
        # check whether problematic line is part of the context we want
        # to show (i.e. a few lines before & after problematic line)
        if (abs(lineno - curr_line) <= gelb.utils.config.GELB_ERROR_CONTEXT):
            # print each of the selected lines of context
            if lineno == curr_line:
                # special treatment for the problematic line
                line_width = len(line_text)
                click.echo(
                    Fore.RED + f"{lineno:>4}->{line_text}" +
                    Style.RESET_ALL
                )

                click.echo(' ' * (curr_column + 6), nl=False)
                click.echo(
                    Fore.RED + ("^^" + (" " * (line_width - 1))) + (
                        f"[Problem] Re-definition of \"{symbol_name}\" here."
                    ) +
                    Style.RESET_ALL
                )
            else:
                # normal print, for non-problematic line
                click.echo(
                    Fore.BLUE + f"{lineno:>4}  {line_text}" + Style.RESET_ALL
                )
    # print bottom gutter (..., if lines of context are not near the end)
    if (lines_in_file - prev_line) > gelb.utils.config.GELB_ERROR_CONTEXT:
        click.echo(' ' * 6 + Fore.BLUE + '...' + Style.RESET_ALL)


def show_error_in_src(line, column, error, hint):
    lines_in_file = count_lines_in_program()

    click.echo()  # newline
    # print top gutter (..., if lines of context are not near the start)
    if line > (gelb.utils.config.GELB_ERROR_CONTEXT + 1):
        click.echo(' ' * 6 + Fore.BLUE + '...' + Style.RESET_ALL)
    # iterate over all lines in the file
    for (lineno, line_text) in iterate_over_lines_in_src():
        # check whether problematic line is part of the context we want
        # to show (i.e. a few lines before & after problematic line)
        if (abs(lineno - line) <= gelb.utils.config.GELB_ERROR_CONTEXT):
            # print each of the selected lines of context
            if lineno == line:
                # special treatment for the problematic line
                line_width = len(line_text)
                click.echo(
                    Fore.RED + f"{lineno:>4}->{line_text}" +
                    Style.RESET_ALL
                )

                click.echo(' ' * (column + 6), nl=False)
                click.echo(
                    Fore.RED + ("^^" + (" " * (line_width - 1))) +
                    f"[Problem] {error}" +
                    Style.RESET_ALL
                )

                click.echo(' ' * (column + 6), nl=False)
                click.echo(
                    Fore.GREEN + (
                            " " * (line_width + 1) +
                            f"[Hint] {hint}"
                    ) +
                    Style.RESET_ALL
                )
            else:
                # normal print, for non-problematic line
                click.echo(
                    Fore.BLUE + f"{lineno:>4}  {line_text}" + Style.RESET_ALL
                )
    # print bottom gutter (..., if lines of context are not near the end)
    if (lines_in_file - line) > gelb.utils.config.GELB_ERROR_CONTEXT:
        click.echo(' ' * 6 + Fore.BLUE + '...' + Style.RESET_ALL)
