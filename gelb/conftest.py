#!/usr/bin/env python3

from gelb.utils.misc import invoke_antlr4_tool
import gelb.utils.config


def pytest_sessionstart(session):
    """
    Called after the Session object has been created and before performing
    collection and entering the run test loop.
    """
    gelb.utils.config.GELB_PRODUCTION_MODE = False  # makes GeLB exceptions
    # non-fatal
    invoke_antlr4_tool()
