#!/usr/bin/env python3

import click
from colorama import Fore, Style

import utils.config


feedback_on_slack_hint = (
    f"If you are a GeLB user, please report this error on our"
    f" Slack #feedback channel (https://gelb-devs.slack.com)."
)

learning_gelb_hint = (
    f"Please visit https://gelb-lang.org to learn more about the GeLB "
    f"programming language and about writing GeLB programs."
)


def iterate_over_lines_in_src():
    # iterate over lines in GELB_SRC_RAW
    current_lineno = 1
    previous_nl = -1
    while True:
        next_nl = utils.config.GELB_SRC_RAW.find('\n', previous_nl + 1)
        if next_nl < 0:
            break
        yield (current_lineno,
               utils.config.GELB_SRC_RAW[(previous_nl + 1): next_nl])
        previous_nl = next_nl
        current_lineno += 1


def count_lines_in_program():
    no_lines = 0
    for (lineno, line_text) in iterate_over_lines_in_src():
        no_lines += 1
    return no_lines


def show_source_with_annotation(line, column, click_color,
                                annotation, hint=None):
    lines_in_file = count_lines_in_program()

    click.echo()  # newline
    # print top gutter (..., if lines of context are not near the start)
    if line > (utils.config.GELB_ERROR_CONTEXT + 1):
        click.echo(' ' * 6 + Fore.BLUE + '...' + Style.RESET_ALL)
    # iterate over all lines in the file
    for (lineno, line_text) in iterate_over_lines_in_src():
        # check whether problematic line is part of the context we want
        # to show (i.e. a few lines before & after problematic line)
        if abs(lineno - line) <= utils.config.GELB_ERROR_CONTEXT:
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
                    click_color + ("^^" + (" " * (line_width - 1))) +
                    f"[Problem] {annotation}" +
                    Style.RESET_ALL
                )

                if hint:
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
    if (lines_in_file - line) > utils.config.GELB_ERROR_CONTEXT:
        click.echo(' ' * 6 + Fore.BLUE + '...' + Style.RESET_ALL)


def show_error_in_src(line, column, error, hint):
    show_source_with_annotation(line, column, Fore.RED, error, hint)


def show_double_definition_error(
        curr_line,
        curr_column,
        prev_line,
        prev_column,
        symbol_name, symbol_tag):
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
        f"Re-definition of"
        f" "
        f"{click.style(symbol_name, underline=True) + Fore.RED}"
        f" here."
    )
