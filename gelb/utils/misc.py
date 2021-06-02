#!/usr/bin/env python3

from pathlib import Path
import sys
import click
from colorama import Fore, Style
from fnmatch import fnmatch


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


def ensure_input_file_has_gelb_extension(input_file, verbose):
    info_to_term("ensuring that input file has \".gelb\" file extension", verbose)
    if not fnmatch(input_file, "*.gelb"):
        fatal_error_with_hint_to_term(
            f"input-file \"{input_file}\" does not have the \".gelb\" extension",
            f"give me a file that ends in \".gelb\""
        )
    info_to_term("OK!", verbose)


def ensure_input_file_exists_and_get_full_path(input_file, verbose):
    info_to_term(
        "getting full input file path (and ensuring that it exists)",
        verbose
    )
    try:
        path = Path(input_file).resolve(strict=True)
        info_to_term("OK!", verbose)
        return path
    except FileNotFoundError:
        fatal_error_with_hint_to_term(
            f"couldn't read input file \"{input_file}\"",
            "specify a file which exists"
        )


def load_file(input_file, verbose):
    ensure_input_file_has_gelb_extension(input_file, verbose)
    path = ensure_input_file_exists_and_get_full_path(input_file, verbose)

    info_to_term(f"loading input-file (=\"{path}\")", verbose)
    try:
        src_raw = path.read_text(encoding='utf-8')
        info_to_term("OK!", verbose)
        return src_raw
    except OSError:
        fatal_error_with_hint_to_term(
            f"couldn't read input file \"{path}\"",
            f"change permissions for file \"{path}\", "
            f"to allow gelbc to read it"
        )
