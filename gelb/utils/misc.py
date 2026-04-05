#!/usr/bin/env python3

from pathlib import Path
from fnmatch import fnmatch
from subprocess import run
import pathlib
import re
import os
import shutil
from importlib.metadata import distributions, version, PackageNotFoundError

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
    # Generate into a scratch directory beside the target and move the
    # results into place afterwards.  The generated files are deleted
    # only once their replacements exist: this function runs whenever a
    # process fails to import them, so a process that observed them
    # missing (or being written) while another regenerated them must
    # not delete them for everyone else, and a failed tool run (no Java
    # on this machine, say) must leave the tree as it was: an earlier
    # version deleted the live parser before invoking the tool, and a
    # failed run lost it.
    scratch_dir = output_dir / f".antlr4_tmp_{os.getpid()}"
    shutil.rmtree(scratch_dir, ignore_errors=True)
    scratch_dir.mkdir(parents=True)

    # ANTLR embeds whatever input-file path we hand it into the
    # "# Generated from <path> by ANTLR ..." header at the top of every
    # generated file. Passing an absolute path makes that header host-
    # specific (`/home/user/...` on Linux, `/Users/user/...` on
    # macOS, `C:\Users\...` on Windows), which produces a noisy diff
    # every time the grammar is regenerated on a different machine.
    # Run ANTLR with cwd=repo_root and pass POSIX-relative paths so the
    # header is identical across hosts and OSes.
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    grammar_arg = grammar_path.resolve().relative_to(repo_root).as_posix()
    output_arg = scratch_dir.resolve().relative_to(repo_root).as_posix()

    # Work around an upstream antlr4-tools bug: its `latest_version()` queries
    # Maven Central's `solrsearch/select` endpoint to discover the newest
    # antlr4 jar, but that endpoint now returns HTTP 400 (the search API was
    # changed). The fallback then tries to list `~/.m2/repository/org/antlr/
    # antlr4/`, which doesn't exist on machines without a prior Maven install.
    # Both failures cascade into a misleading "ANTLR4 Java tool failed" error.
    #
    # Pin the ANTLR jar version explicitly via ANTLR4_TOOLS_ANTLR_VERSION,
    # using the version of the antlr4-python3-runtime package that's already
    # installed in this environment. ANTLR's compatibility policy requires the
    # runtime and the jar to share the same X.Y.Z version, so reading the
    # runtime version is the canonical source of truth (and it tracks the pin
    # in pyproject.toml automatically -- no second place to update).
    env = os.environ.copy()
    if "ANTLR4_TOOLS_ANTLR_VERSION" not in env:
        try:
            env["ANTLR4_TOOLS_ANTLR_VERSION"] = version("antlr4-python3-runtime")
        except PackageNotFoundError:
            # Should never happen -- antlr4-python3-runtime is a hard dep -- but
            # if it does, fall through and let antlr4-tools attempt its own
            # (broken) discovery so the user sees the real error.
            pass

    # invoke ANTLR4 tool via antlr4-tools
    #
    # `-Xexact-output-dir` tells ANTLR to use `-o` literally rather than
    # appending the grammar's directory components -- without it,
    # `-o gelb/antlr_part/generated_code gelb/antlr_part/grammars/GeLB.g4`
    # would generate into `generated_code/gelb/antlr_part/grammars/`.
    antlr4_tool_stat = run(["antlr4",
                           "-Werror",  # treat warnings as errors
                           "-Dlanguage=Python3",
                           "-no-listener",
                           "-visitor",
                           "-Xexact-output-dir",
                           "-o", output_arg,
                           grammar_arg],
                          cwd=str(repo_root),
                          env=env)
    generated = sorted(scratch_dir.glob("GeLB*"))
    if antlr4_tool_stat.returncode != 0 or not generated:
        shutil.rmtree(scratch_dir, ignore_errors=True)
        raise exceptions.GeLBExAntlr4JavaToolFailed(antlr4_tool_stat)
    for produced in generated:
        os.replace(produced, output_dir / produced.name)
    shutil.rmtree(scratch_dir, ignore_errors=True)

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
