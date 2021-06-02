#!/usr/bin/env python3

from pathlib import Path
from fnmatch import fnmatch
from subprocess import run
import pathlib
import pkg_resources

from gelb.utils.error_reporting import *


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


def cleanup_antlr4_generated_files(output_dir):
    run(["rm", "-f", output_dir / "GeLB.interp"])
    run(["rm", "-f", output_dir / "GeLB.tokens"])
    run(["rm", "-f", output_dir / "GeLBLexer.interp"])
    run(["rm", "-f", output_dir / "GeLBLexer.py"])
    run(["rm", "-f", output_dir / "GeLBLexer.tokens"])
    run(["rm", "-f", output_dir / "GeLBParser.py"])
    run(["rm", "-f", output_dir / "GeLBListener.py"])
    run(["rm", "-f", output_dir / "GeLBVisitor.py"])


def find_antlr4_tool_path():
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


def ensure_antlr4_python3_runtime_is_present():
    # check that the =antlr4-python3-runtime= Python package is installed
    installed_packages = {pkg.key for pkg in pkg_resources.working_set}
    if "antlr4-python3-runtime" not in installed_packages:
        fatal_error_to_term("Python3 package \"antlr4-python3-runtime\""
                            " not installed")


def invoke_antlr4_tool():
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
        fatal_error_with_hint_to_term(
            f"ANTLR4 Java tool failed to compile the grammar\n"
            f"\n\treturn code: {antlr4_tool_stat.returncode}"
            f"\n\tstdout: {antlr4_tool_stat.stdout}"
            f"\n\tstderr: {antlr4_tool_stat.stderr}",
            "fix the grammar file(s)"
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
