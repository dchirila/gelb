#!/usr/bin/env python3

from antlr4.error.ErrorListener import ErrorListener

from gelb.utils.exceptions import (
    GeLBExSyntaxError
)


class ParsingError(ErrorListener):
    def syntaxError(self, recognizer, offending_symbol, line, column, msg, e):
        error = "Your GeLB program contains a syntax error."
        hint = f"{msg}"
        raise GeLBExSyntaxError(line, column, error, hint)
