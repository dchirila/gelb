#!/usr/bin/env python3

from utils.misc import invoke_antlr4_tool
import utils.config


def pytest_sessionstart(session):
    """
    Called after the Session object has been created and before performing
    collection and entering the run test loop.
    """
    invoke_antlr4_tool()
