#!/usr/bin/env python3

import os
import pathlib
import platform
import subprocess

from gelb.utils.misc import invoke_antlr4_tool
import gelb.utils.config


def _ensure_java_on_path():
    """Mirror the macOS Java auto-detect from ``scripts/regenerate_antlr.sh``.

    macOS ships ``/usr/bin/java`` as a stub launcher that exits non-zero
    when no real JDK is installed; without an explicit PATH entry,
    ``invoke_antlr4_tool()`` then fails with the misleading "Unable to
    locate a Java Runtime" message.  When a Homebrew OpenJDK install is
    present we wire it up automatically so a fresh ``brew install
    openjdk`` is the only setup the user needs.

    No-op on Linux (``java`` is normally on PATH via the distro's
    alternatives system) and when ``JAVA_HOME`` is already set.
    """
    if platform.system() != 'Darwin':
        return
    if os.environ.get('JAVA_HOME'):
        return
    try:
        subprocess.run(['java', '-version'], check=True,
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=5)
        return  # working java already on PATH
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        pass
    for candidate in ('/opt/homebrew/opt/openjdk',
                      '/usr/local/opt/openjdk'):
        if pathlib.Path(candidate, 'bin', 'java').is_file():
            os.environ['JAVA_HOME'] = candidate
            os.environ['PATH'] = f'{candidate}/bin:{os.environ.get("PATH", "")}'
            return


def pytest_sessionstart(session):
    """
    Called after the Session object has been created and before performing
    collection and entering the run test loop.
    """
    _ensure_java_on_path()
    invoke_antlr4_tool()
