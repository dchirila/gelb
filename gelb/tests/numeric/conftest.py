"""Compile one independent reference executable for the entire corpus."""

import json
import shutil
import subprocess

import pytest

from .cases import ACTIVE_SEED, CASES, RANDOM_COUNT, oracle_source


@pytest.fixture(scope="session")
def numeric_oracle(tmp_path_factory):
    compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        pytest.skip("a C++17 compiler is needed for the independent numeric oracle")
    work = tmp_path_factory.mktemp("numeric_reference")
    source, executable = work / "reference.cpp", work / "reference"
    source.write_text(oracle_source(CASES))
    command = [compiler, "-std=c++17", "-O0", "-fno-fast-math", "-ffp-contract=off",
               str(source), "-o", str(executable)]
    built = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    (work / "build.log").write_text(built.stdout + built.stderr)
    try:
        assert built.returncode == 0, f"{command}\n{built.stdout}\n{built.stderr}"
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=30, check=False)
    finally:
        executable.unlink(missing_ok=True)
    (work / "reference.txt").write_text(run.stdout)
    assert run.returncode == 0, run.stderr
    result = {}
    for line in run.stdout.splitlines():
        name, coordinate, raw, stored, array_sum = line.split()
        result.setdefault(name, {})[int(coordinate)] = {
            "raw": float.fromhex(raw), "stored": float.fromhex(stored),
            "array_sum": float.fromhex(array_sum)}
    assert set(result) == {case.name for case in CASES}
    assert all(set(result[case.name]) == set(range(case.cells)) for case in CASES)
    (work / "manifest.json").write_text(json.dumps({
        "seed": ACTIVE_SEED, "random_count": RANDOM_COUNT, "compile_command": command,
        "compiler_version": subprocess.run([compiler, "--version"], capture_output=True,
                                           text=True, timeout=10, check=False).stdout,
        "cases": [vars(case) for case in CASES], "reference": result,
    }, indent=2) + "\n")
    return result
