#!/usr/bin/env python3

from antlr4.error.ErrorListener import ErrorListener

from gelb.utils.output_to_terminal import fatal_error_with_hint_to_term


class ParsingError(ErrorListener):
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        fatal_error_with_hint_to_term(
            "parsing error TODO-explain-more",
            # hint
            f"here is some debugging information:"
            f"\n\ttype(recognizer) = {type(recognizer)}"
            f"\n\trecognizer = {recognizer}"
            f"\n\ttype(offendingSymbol) = {type(offendingSymbol)}"
            f"\n\toffendingSymbol = {offendingSymbol}"
            f"\n\tline = {line}"
            f"\n\tcolumn = {column}"
            f"\n\tmsg = {msg}"
            f"\n\ttype(e) = {type(e)}"
            f"\n\te = {e}"
        )

    def printContext(self, TODO_all_info_needed_for_highlighting):
        raise NotImplementedError()
