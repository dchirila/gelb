#!/usr/bin/env python3

from pathlib import Path
from fnmatch import fnmatch
from subprocess import run
import pathlib
import re
import os
from importlib.metadata import distributions

from gelb.utils import exceptions
from gelb.utils import config


def initialize_reserved_keywords():
    """
    Initialize GELB_RESERVED_KEYWORDS from the lexer's literal names.
    
    This extracts keywords from the ANTLR-generated lexer and filters them
    to include only valid identifier-like keywords.
    
    Safe to call multiple times - only initializes if not already done.
    """
    if config.GELB_RESERVED_KEYWORDS is not None:
        return  # Already initialized
        
    try:
        from gelb.antlr_part.generated_code.GeLBLexer import GeLBLexer
        literal_names = GeLBLexer.literalNames

        reg = re.compile(r'^[a-zA-Z0-9_]+$')
        config.GELB_RESERVED_KEYWORDS = list(
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
    except ImportError:
        # ANTLR files not available - will be initialized later
        pass


def ensure_input_file_has_gelb_extension(input_file):
    if not fnmatch(input_file, "*.gelb"):
        raise exceptions.GeLBExIncorrectInputFileExtension(input_file)


def ensure_input_file_exists_and_get_full_path(input_file):
    try:
        path = Path(input_file).resolve(strict=True)
        return path
    except:
        suggest_files = find_gelb_files_in_cwd()
    raise exceptions.GeLBExCouldNotFindInputFile(input_file, suggest_files)


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

    NOTE: The users should not encounter this problem, because =uv sync=
    should take care of the package-dependencies.
    """
    installed_packages = [str(d.metadata['Name']) for d in distributions()]
    if package_name not in installed_packages:
        raise exceptions.GeLBExPython3PackageMissing(package_name)


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
        raise exceptions.GeLBExGrammarFileNotFound(grammar_path)
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
        raise exceptions.GeLBExAntlr4JavaToolFailed(antlr4_tool_stat)

    # Initialize reserved keywords from the newly generated lexer
    initialize_reserved_keywords()


def load_file(input_file):
    ensure_input_file_has_gelb_extension(input_file)
    path = ensure_input_file_exists_and_get_full_path(input_file)

    try:
        config.GELB_SRC_RAW = path.read_text(encoding='utf-8')
        return config.GELB_SRC_RAW
    except OSError:
        raise exceptions.GeLBExCouldNotReadInputFile(path)


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
        if not exceptions.running_within_pytest():
            raise exceptions.GeLBExEmptyInputFile(
                config.GELB_FILE_NAME
            )
        else:  # testing, so probably no filename
            raise exceptions.GeLBExEmptyInputFile()
