#!/usr/bin/env python3

from antlr4.error.ErrorListener import ErrorListener

from gelb.utils.exceptions import *


class ParsingError(ErrorListener):
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        error = "[Problem] We found a syntax error in your file"
        hint = f"[Hint] ANTLR4 says: {msg}"
        raise GeLBExSyntaxError(line, column, error, hint)
