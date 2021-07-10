#!/usr/bin/env python3


class CodeRange:
    def __init__(self, start_line, start_col, stop_line, stop_col):
        self.start_line = start_line
        self.start_col = start_col
        self.stop_line = stop_line
        self.stop_col = stop_col

    def __gt__(self, other):
        return (self.start_line > other.start_line) or (
                (self.start_line == other.start_line) and
                (self.start_col > other.start_col)
        )

    def __str__(self):
        return (
            f"(CodeRange"
            f" {self.start_line} {self.start_col}"
            f" {self.stop_line} {self.stop_col}"
            f")"
        )

def code_range_from_ctx(ctx_or_list_of_ctx):
    if isinstance(ctx_or_list_of_ctx, list):
        return CodeRange(
            ctx_or_list_of_ctx[0].start.line,
            ctx_or_list_of_ctx[0].start.column,
            ctx_or_list_of_ctx[-1].stop.line,
            ctx_or_list_of_ctx[-1].stop.column
        )
    else:
        return CodeRange(
            ctx_or_list_of_ctx.start.line,
            ctx_or_list_of_ctx.start.column,
            ctx_or_list_of_ctx.stop.line,
            ctx_or_list_of_ctx.stop.column
        )
