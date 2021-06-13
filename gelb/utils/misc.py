#!/usr/bin/env python3

from pathlib import Path
from fnmatch import fnmatch
from subprocess import run
import pathlib
import os
import pkg_resources

from gelb.utils.output_to_terminal import *
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
    'lattice_constants',
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


def ensure_input_file_has_gelb_extension(input_file, verbose):
    verbose_progress_message(
        "ensuring that input file has \".gelb\" file extension",
        verbose
    )
    if not fnmatch(input_file, "*.gelb"):
        verbose_progress_message("FAIL", verbose)
        error_with_hint_to_term(
            f"input-file \"{input_file}\" does not have the \".gelb\" extension",
            f"give me a file that ends in \".gelb\""
        )
    verbose_progress_message("OK", verbose)


def ensure_input_file_exists_and_get_full_path(input_file, verbose):
    verbose_progress_message(
        "getting full input file path (and ensuring that it exists)",
        verbose
    )
    try:
        path = Path(input_file).resolve(strict=True)
        verbose_progress_message("OK", verbose)
        return path
    except FileNotFoundError:
        verbose_progress_message("FAIL", verbose)
        gelb_files_in_cwd = find_gelb_files_in_cwd()
        if gelb_files_in_cwd:
            extra_hint = (
                f" Did you mean one of the following files "
                f"{gelb_files_in_cwd}?"
            )
        else:
            extra_hint = ""
        error_with_hint_to_term(
            f"couldn't read input file \"{input_file}\"",
            f"specify a file which exists.{extra_hint}"
        )


def cleanup_antlr4_generated_files(output_dir, verbose=False):
    run(["rm", "-f", output_dir / "GeLB.interp"])
    run(["rm", "-f", output_dir / "GeLB.tokens"])
    run(["rm", "-f", output_dir / "GeLBLexer.interp"])
    run(["rm", "-f", output_dir / "GeLBLexer.py"])
    run(["rm", "-f", output_dir / "GeLBLexer.tokens"])
    run(["rm", "-f", output_dir / "GeLBParser.py"])
    run(["rm", "-f", output_dir / "GeLBListener.py"])
    run(["rm", "-f", output_dir / "GeLBVisitor.py"])


def find_antlr4_tool_path(verbose=False):
    # check that the ANTLR4 Java-lib is present
    # NOTE: To avoid possible issues with incompatible ANTLR4 versions, this
    # Java library is included within the GeLB repository (so normally it
    # should be there, unless you removed it)
    lib_dir = pathlib.Path(__file__).parent.parent.parent / 'lib'
    antlr4_lib_path = lib_dir / 'antlr-4.9.2-complete.jar'
    if not antlr4_lib_path.is_file():
        fatal_error_to_term("Antlr4 java library file not found")
    else:
        return antlr4_lib_path


def ensure_antlr4_python3_runtime_is_present(verbose=False):
    # check that the =antlr4-python3-runtime= Python package is installed
    installed_packages = {pkg.key for pkg in pkg_resources.working_set}
    if "antlr4-python3-runtime" not in installed_packages:
        fatal_error_to_term("Python3 package \"antlr4-python3-runtime\""
                            " not installed")


def invoke_antlr4_tool(verbose=False):
    """
    Invoke the ANTLR4 Java tool.

    This generates =GeLB{Lexer,Parser,Visitor}.py=, based on the =GeLB.g4= grammar.
    """
    antlr4_lib_path = find_antlr4_tool_path()
    ensure_antlr4_python3_runtime_is_present()
    # infer the path to the GeLB language grammar
    grammar_dir = pathlib.Path(__file__).parent.parent / 'antlr4' / 'grammars'
    output_dir = pathlib.Path(__file__).parent.parent / 'antlr4' / 'generated_code'
    grammar_path = grammar_dir / "GeLB.g4"
    if not grammar_path.is_file():
        fatal_error_to_term(f"{grammar_path} grammar file not found")
    cleanup_antlr4_generated_files(output_dir)  # to be on the safe side

    ## invoke ANTLR4 Java tool
    antlr4_tool_stat = run(["java",
                            "-Xmx500M",
                            "-jar", antlr4_lib_path,
                            "-Werror",  # treat warnings as errors
                            "-Dlanguage=Python3",
                            "-no-listener",
                            "-visitor",
                            "-o",
                            output_dir,
                            grammar_path])
    if antlr4_tool_stat.returncode != 0:
        error_with_hint_to_term(
            f"ANTLR4 Java tool failed to compile the grammar\n"
            f"\n\treturn code: {antlr4_tool_stat.returncode}"
            f"\n\tstdout: {antlr4_tool_stat.stdout}"
            f"\n\tstderr: {antlr4_tool_stat.stderr}",
            "fix the grammar file(s)"
        )


def load_file(input_file, verbose=False):
    ensure_input_file_has_gelb_extension(input_file, verbose)
    path = ensure_input_file_exists_and_get_full_path(input_file, verbose)

    verbose_progress_message(f"loading input-file (=\"{path}\")", verbose)
    try:
        gelb.utils.config.GELB_SRC_RAW = path.read_text(encoding='utf-8')
        verbose_progress_message("OK", verbose)
        return gelb.utils.config.GELB_SRC_RAW
    except OSError:
        verbose_progress_message("FAIL", verbose)
        error_with_hint_to_term(
            f"couldn't read input file \"{path}\"",
            f"change permissions for file \"{path}\", "
            f"to allow gelbc to read it"
        )


def iterate_over_lines_in_src():
    # iterate over lines in GELB_SRC_RAW
    current_lineno = 1
    previous_nl = -1
    while True:
        next_nl = gelb.utils.config.GELB_SRC_RAW.find('\n', previous_nl + 1)
        if next_nl < 0: break
        yield (current_lineno,
               gelb.utils.config.GELB_SRC_RAW[(previous_nl + 1): next_nl])
        previous_nl = next_nl
        current_lineno += 1

def print_error_context(input_file, line, column):
    raise NotImplementedError()


def find_gelb_files_in_cwd():
    """
    Finds (and returns list of) GeLB files in the current working directory.
    """
    gelb_files_in_cwd = []
    for file in os.listdir('.'):
        if fnmatch(file, '*.gelb'):
            gelb_files_in_cwd.append(file)
    return gelb_files_in_cwd


def ensure_file_is_not_empty_or_whitespace(file_as_string, verbose):
    verbose_progress_message("ensuring file is not empty", verbose)
    if len(file_as_string) != 0:
        verbose_progress_message("OK", verbose)
    else:
        verbose_progress_message("FAIL", verbose)
        error_with_hint_to_term(
            "input file is empty",
            learning_gelb_hint
        )

    verbose_progress_message(
        "ensuring file contains more than just whitespace",
        verbose
    )
    if not file_as_string.isspace():
        verbose_progress_message("OK", verbose)
    else:
        verbose_progress_message("FAIL", verbose)
        error_with_hint_to_term(
            "input file contains only whitespace",
            learning_gelb_hint
        )


def show_error_in_src(line, column, error, hint):
    lines_in_file = 0
    for (lineno, line_text) in iterate_over_lines_in_src():
        lines_in_file += 1

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
                    f"{error}" +
                    Style.RESET_ALL
                )

                click.echo(' ' * (column + 6), nl=False)
                click.echo(
                    Fore.GREEN + (
                            " " * (line_width + 1) +
                            f"{hint}"
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
