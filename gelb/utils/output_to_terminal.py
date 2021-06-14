#!/usr/bin/env python3

import sys
import click
from colorama import Fore, Style


def show_fatal_error_message_without_abort(error_message):
    # display the error message
    click.echo(Fore.RED + f"[Problem] {error_message}" + Style.RESET_ALL)
    # say that it was a fatal error
    click.echo(Fore.RED + "\ngelbc-ERROR:", nl=False)
    click.echo(
        " aborting compilation due to previous error\n" + Style.RESET_ALL
    )


def error_with_hint_to_term(error_message, hint_message):
    show_fatal_error_message_without_abort(error_message)
    # display the hint
    click.echo(Fore.GREEN + f"[Hint] {hint_message}" + Style.RESET_ALL)


def info_to_term(message):
    click.echo(Fore.BLUE + "gelbc-INFO:" + Style.RESET_ALL, nl=False)
    click.echo(f" {message}")
