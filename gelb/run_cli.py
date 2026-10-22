"""``gelb-run``, the compile-and-run command, as an installed entry point.

The runner is the bash script ``gelb/scripts/gelb-run`` (package data).
This module is what ``[project.scripts]`` points ``gelb-run`` at: it
replaces the current process with that script, passing the arguments
and the environment through unchanged, so that ``gelb-run`` is the same
plain command in a source checkout as in a packaged installation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "scripts" / "gelb-run"


def main() -> None:
    if not SCRIPT.is_file():
        sys.exit(f"gelb-run: the runner script is missing from this installation: {SCRIPT}")
    argv = [str(SCRIPT), *sys.argv[1:]]
    try:
        os.execv(str(SCRIPT), argv)
    except PermissionError:
        # A copy without the executable bit (some package builds drop it):
        # the script is bash either way.
        os.execvp("bash", ["bash", *argv])


if __name__ == "__main__":
    main()
