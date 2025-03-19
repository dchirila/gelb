#!/usr/bin/env python3

from pathlib import Path
from fnmatch import fnmatch
from subprocess import run
import pathlib
import re
import os
from importlib.metadata import distributions

import utils.exceptions
import utils.config


def ensure_input_file_has_gelb_extension(input_file):
    if not fnmatch(input_file, "*.gelb"):
        raise utils.exceptions.GeLBExIncorrectInputFileExtension(input_file)


def ensure_input_file_exists_and_get_full_path(input_file):
    try:
        path = Path(input_file).resolve(strict=True)
        return path
    except:
        suggest_files = find_gelb_files_in_cwd()
    raise utils.exceptions.GeLBExCouldNotFindInputFile(input_file, suggest_files)


def cleanup_antlr4_generated_files(output_dir):
    files_to_remove = ["GeLB.interp", "GeLB.tokens", "GeLBLexer.interp", "GeLBLexer.py",
                       "GeLBLexer.tokens", "GeLBParser.py", "GeLBListener.py", "GeLBVisitor.py"]
    for file in files_to_remove:
        file_path = os.path.join(output_dir, file)
        if os.path.exists(file_path):
            os.remove(file_path)


def ensure_python3_package_is_present(package_name):
    """
    Generic utility-function, for checking that a Python3 package required by
    GeLB is actually installed.

    NOTE: The users should not encounter this problem, because =pip install=
    should take care of the package-dependencies.
    """
    installed_packages = [str(d.metadata['Name']) for d in distributions()]
    if package_name not in installed_packages:
        raise utils.exceptions.GeLBExPython3PackageMissing(package_name)


def invoke_antlr4_tool():
    """
    Invoke the ANTLR4 tool using antlr4-tools package.

    This generates =GeLB{Lexer,Parser,Visitor}.py=, based on the =GeLB.g4=
    grammar.
    """
    ensure_python3_package_is_present("antlr4-tools")
    ensure_python3_package_is_present("antlr4-python3-runtime")
    
    # infer the path to the GeLB language grammar
    grammar_dir = pathlib.Path(__file__).parent.parent/'antlr_part'/'grammars'
    output_dir = pathlib.Path(__file__).parent.parent/'antlr_part'/'generated_code'
    grammar_path = grammar_dir / "GeLB.g4"
    if not grammar_path.is_file():
        raise utils.exceptions.GeLBExGrammarFileNotFound(grammar_path)
    cleanup_antlr4_generated_files(output_dir)  # to be on the safe side

    # invoke ANTLR4 tool via antlr4-tools
    antlr4_tool_stat = run(["antlr4",
                           "-Werror",  # treat warnings as errors
                           "-Dlanguage=Python3",
                           "-no-listener",
                           "-visitor",
                           "-o", str(output_dir),
                           str(grammar_path)])
    if antlr4_tool_stat.returncode != 0:
        raise utils.exceptions.GeLBExAntlr4JavaToolFailed(antlr4_tool_stat)

    # obtain the list of reserved keywords (directly from the lexer); this
    # has the advantage of always being up-to-date.
    if utils.config.GELB_RESERVED_KEYWORDS is None:
        # for auto-deducing reserved keywords
        from antlr_part.generated_code.GeLBLexer import GeLBLexer
        literal_names = GeLBLexer.literalNames

        reg = re.compile(r'^[a-zA-Z0-9_]+$')
        utils.config.GELB_RESERVED_KEYWORDS = list(
            filter(
                lambda kwd: bool(reg.match(kwd)),
                list(
                    filter(
                        lambda kwd: 'INVALID' not in kwd,
                        [kwd.replace("'", "") for kwd in literal_names]
                    )
                )
            )
        )


def load_file(input_file):
    ensure_input_file_has_gelb_extension(input_file)
    path = ensure_input_file_exists_and_get_full_path(input_file)

    try:
        utils.config.GELB_SRC_RAW = path.read_text(encoding='utf-8')
        return utils.config.GELB_SRC_RAW
    except OSError:
        raise utils.exceptions.GeLBExCouldNotReadInputFile(path)


def find_gelb_files_in_cwd():
    """
    Finds (and returns list of) GeLB files in the current working directory.
    """
    gelb_files_in_cwd = []
    for file in os.listdir('.'):
        if fnmatch(file, '*.gelb'):
            gelb_files_in_cwd.append(file)
    return gelb_files_in_cwd


def ensure_file_is_not_empty_or_whitespace(file_as_string):
    if (len(file_as_string) == 0) or file_as_string.isspace():
        if not utils.exceptions.running_within_pytest():
            raise utils.exceptions.GeLBExEmptyInputFile(
                utils.config.GELB_FILE_NAME
            )
        else:  # testing, so probably no filename
            raise utils.exceptions.GeLBExEmptyInputFile()
