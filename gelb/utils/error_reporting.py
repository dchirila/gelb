#!/usr/bin/env python3

import sys
import click
from colorama import Fore, Style


def show_fatal_error_message_without_abort(error_message):
    # display the error message
    click.echo(Fore.RED + "<<<gelbc-ERROR>>>" + Style.RESET_ALL, nl=False)
    click.echo(f" {error_message}")
    # say that it was a fatal error
    click.echo(Fore.RED + "<<<gelbc-ERROR>>>" + Style.RESET_ALL, nl=False)
    click.echo(" aborting due to previous error")


def fatal_error_to_term(error_message):
    show_fatal_error_message_without_abort(error_message)
    sys.exit(1)  # make error fatal (i.e. abort)


def fatal_error_with_hint_to_term(error_message, hint_message):
    show_fatal_error_message_without_abort(error_message)
    # display the hint
    click.echo(Fore.GREEN + "<<<gelbc-HINT >>>" + Style.RESET_ALL, nl=False)
    click.echo(f" {hint_message}")
    sys.exit(1)  # make error fatal (i.e. abort)


def info_to_term(message, verbose):
    if verbose:
        click.echo(Fore.BLUE + "<<<gelbc-INFO >>>" + Style.RESET_ALL, nl=False)
        click.echo(f" {message}")
