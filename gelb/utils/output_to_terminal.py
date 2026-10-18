#!/usr/bin/env python3

import click
from colorama import Fore, Style


def show_fatal_error_message_without_abort(error_message):
    # display the error message
    click.echo(Fore.RED + f"[Problem] {error_message}\n" + Style.RESET_ALL)


def error_with_hint_to_term(error_message, hint_message):
    show_fatal_error_message_without_abort(error_message)
    # display the hint
    click.echo(Fore.GREEN + f"[Hint] {hint_message}" + Style.RESET_ALL)


def warning_with_hint_to_term(warning_message, hint_message, source_line=None):
    """Display a non-fatal warning with a hint.

    When gelbc is in diagnostics mode (config.DIAGNOSTICS_MODE), the
    warning is collected into a list that gelbc later emits as JSON,
    and nothing is written to stderr -- stderr noise would corrupt the
    machine-readable stdout contract.  ``source_line`` (1-based, or
    None) is where the JSON diagnostic points.
    """
    from gelb.utils import config
    if getattr(config, 'DIAGNOSTICS_MODE', False):
        config.DIAGNOSTICS_WARNINGS.append(
            (warning_message, hint_message, source_line))
        return
    if source_line is not None:
        from gelb.utils.error_utils import (
            show_source_with_annotation, source_anchor_column,
        )
        show_source_with_annotation(
            source_line, source_anchor_column(source_line, warning_message), Fore.YELLOW,
            warning_message, hint_message, label="Warning", err=True,
        )
        return
    click.echo(
        Fore.YELLOW + f"[Warning] {warning_message}\n" + Style.RESET_ALL,
        err=True,
    )
    click.echo(
        Fore.GREEN + f"[Hint] {hint_message}" + Style.RESET_ALL,
        err=True,
    )
