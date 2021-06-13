#!/usr/bin/env python3

from pathlib import Path
from fnmatch import fnmatch
from subprocess import run
import pathlib
import os
import pkg_resources

from gelb.utils.output_to_terminal import *
from gelb.utils.exceptions import *
import gelb.utils.config


def ensure_input_file_has_gelb_extension(input_file, verbose):
    if not fnmatch(input_file, "*.gelb"):
        raise GeLBExIncorrectInputFileExtension(input_file)


def ensure_input_file_exists_and_get_full_path(input_file, verbose):
    try:
        path = Path(input_file).resolve(strict=True)
        return path
    except:
        suggest_files = find_gelb_files_in_cwd()
    raise GeLBExCouldNotFindInputFile(input_file, suggest_files)


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

    try:
        gelb.utils.config.GELB_SRC_RAW = path.read_text(encoding='utf-8')
        return gelb.utils.config.GELB_SRC_RAW
    except OSError:
        raise GeLBExCouldNotReadInputFile(path)


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
    if len(file_as_string) == 0:
        raise GeLBExEmptyInputFile()

    if file_as_string.isspace():
        raise GeLBExEmptyInputFile()
