#!/usr/bin/env python3

from antlr4.error.ErrorListener import ErrorListener

from gelb.utils.exceptions import *


class ParsingError(ErrorListener):
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        error = "We found a syntax error in your file"
        hint = f"{msg}"
        raise GeLBExSyntaxError(line, column, error, hint)
