#!/usr/bin/env python3

from antlr4.error.ErrorListener import ErrorListener

from gelb.utils.output_to_terminal import fatal_error_with_hint_to_term
import gelb.utils.config
import click
from colorama import Fore, Style
from gelb.utils.misc import iterate_over_lines_in_src, really_abort


class ParsingError(ErrorListener):
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        lines_in_file = 0
        for (lineno, line_text) in iterate_over_lines_in_src():
            lines_in_file += 1

        click.echo()  # newline
        # print top gutter (..., if lines of context are not near the start)
        if line > (gelb.utils.config.GELB_ERROR_CONTEXT + 1):
            click.echo(' ' * 6 + Fore.GREEN + '...' + Style.RESET_ALL)
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

                    click.echo(' ' * (column+6), nl=False)
                    click.echo(
                        Fore.RED + ("^^" + (" " * (line_width-2))) +
                        " We found a syntax error in your file" +
                        Style.RESET_ALL
                    )

                    click.echo(' ' * (column+6), nl=False)
                    click.echo(
                        Fore.GREEN + (
                                " " * (line_width+1) +
                                f"[Hint] ANTLR4 says: {msg}"
                        ) +
                        Style.RESET_ALL
                    )
                else:
                    # normal print, for non-problematic line
                    click.echo(
                        Fore.GREEN + f"{lineno:>4}  {line_text}" + Style.RESET_ALL
                    )
        # print bottom gutter (..., if lines of context are not near the end)
        if (lines_in_file - line) > gelb.utils.config.GELB_ERROR_CONTEXT:
            click.echo(' ' * 6 + Fore.GREEN + '...' + Style.RESET_ALL)
        really_abort()
