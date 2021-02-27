#!/usr/bin/env python3

import pytest

import pathlib
import pkg_resources
import subprocess


def cleanup_antlr4_generated_files(output_dir):
    subprocess.run(["rm", "-f", output_dir / "GeLB.interp"])
    subprocess.run(["rm", "-f", output_dir / "GeLB.tokens"])
    subprocess.run(["rm", "-f", output_dir / "GeLBLexer.interp"])
    subprocess.run(["rm", "-f", output_dir / "GeLBLexer.py"])
    subprocess.run(["rm", "-f", output_dir / "GeLBLexer.tokens"])
    subprocess.run(["rm", "-f", output_dir / "GeLBParser.py"])
    subprocess.run(["rm", "-f", output_dir / "GeLBListener.py"])
    subprocess.run(["rm", "-f", output_dir / "GeLBVisitor.py"])

def pytest_sessionstart(session):
    """
    Called after the Session object has been created and before performing
    collection and entering the run test loop.
    """

    # check that the ANTLR4 Java-lib is present
    # NOTE: To avoid possible issues with incompatible ANTLR4 versions, this
    # Java library is included within the GeLB repository (so normally it
    # should be there, unless you removed it)
    lib_dir = pathlib.Path(__file__).parent.parent / 'lib'
    antlr4_lib_path = lib_dir / 'antlr-4.8-complete.jar'
    if not antlr4_lib_path.is_file():
        pytest.exit("<<<GeLB:ERROR>>> Antlr4 Java library file not found", returncode=1)

    # check that the =antlr4-python3-runtime= Python package is installed
    installed_packages = {pkg.key for pkg in pkg_resources.working_set}
    if "antlr4-python3-runtime" not in installed_packages:
        pytest.exit("<<<GeLB:ERROR>>> Python3 package \"antlr4-python3-runtime\" not installed",
                    returncode=2)

    # invoke the ANTLR4 Java tool (to generate {Lexer, Parser, Visitor} from the grammar)
    ## infer the path to the GeLB language grammar
    grammar_dir = pathlib.Path(__file__).parent / 'antlr4' / 'grammars'
    output_dir = pathlib.Path(__file__).parent / 'antlr4' / 'generated_code'
    grammar_path = grammar_dir / "GeLB.g4"
    if not grammar_path.is_file():
        pytest.exit("<<<GeLB:ERROR>>> GeLB.g4 grammar file not found", returncode=3)
    cleanup_antlr4_generated_files(output_dir)  # to be on the safe side
    ## invoke ANTLR4 Java tool
    antlr4_tool_stat = subprocess.run(["java",
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
        print("<<<GeLB:ERROR>>> ANTLR4 Java tool failed to compile the grammar")
        print("\n\treturn code:", antlr4_tool_stat.returncode)
        print("\n\tstdout: ", antlr4_tool_stat.stdout)
        print("\n\tstderr: ", antlr4_tool_stat.stderr)
        pytest.exit("<<<GeLB:ERROR>>> Fix the grammar file(s)", returncode=4)
