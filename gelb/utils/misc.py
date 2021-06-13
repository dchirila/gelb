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
        raise GeLBExAntlr4JavaLibNotFound(antlr4_lib_path)
    return antlr4_lib_path


def ensure_python3_package_is_present(package_name):
    """
    Generic utility-function, for checking that a Python3 package required by
    GeLB is actually installed.

    NOTE: The users should not encounter this problem, because =pip install=
    should take care of the package-dependencies.
    """
    installed_packages = {pkg.key for pkg in pkg_resources.working_set}
    if package_name not in installed_packages:
        raise GeLBExPython3PackageMissing(package_name)


def invoke_antlr4_tool(verbose=False):
    """
    Invoke the ANTLR4 Java tool.

    This generates =GeLB{Lexer,Parser,Visitor}.py=, based on the =GeLB.g4= grammar.
    """
    antlr4_lib_path = find_antlr4_tool_path()
    ensure_python3_package_is_present("antlr4-python3-runtime")
    # infer the path to the GeLB language grammar
    grammar_dir = pathlib.Path(__file__).parent.parent / 'antlr4' / 'grammars'
    output_dir = pathlib.Path(__file__).parent.parent / 'antlr4' / 'generated_code'
    grammar_path = grammar_dir / "GeLB.g4"
    if not grammar_path.is_file():
        raise GeLBExGrammarFileNotFound(grammar_path)
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
        raise GeLBExAntlr4JavaToolFailed(antlr4_tool_stat)


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
