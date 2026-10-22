#!/usr/bin/env python3

from antlr4.error.ErrorListener import ErrorListener

from gelb.utils.exceptions import (
    GeLBExSyntaxError
)


class ParsingError(ErrorListener):
    def syntaxError(self, recognizer, offending_symbol, line, column, msg, e):
        error = "Your GeLB program contains a syntax error."
        hint = self._improve_hint(msg, offending_symbol, recognizer)
        raise GeLBExSyntaxError(line, column, error, hint)

    @staticmethod
    def _placeholder_paint(offending_symbol, recognizer):
        """True for the pre-release predicate paint
        ``nodes[F(:, :, ...)] = C;``: a ':' right after '(' or ','
        inside a `nodes[` statement."""
        try:
            stream = recognizer.getTokenStream()
            idx = offending_symbol.tokenIndex
        except Exception:
            return False
        if idx is None or idx <= 0:
            return False
        prev = stream.get(idx - 1).text
        if prev not in ('(', ','):
            return False
        depth = 0
        for i in range(idx - 1, -1, -1):
            text = stream.get(i).text
            if text in (';', '{', '}'):
                return False
            if text == ')':
                depth += 1
            elif text == '(':
                if depth == 0:
                    pass
                else:
                    depth -= 1
            if text == 'nodes':
                return depth == 0
        return False

    @staticmethod
    def _improve_hint(msg, offending_symbol, recognizer=None):
        """Provide clearer hints for common syntax mistakes."""
        token_text = (
            getattr(offending_symbol, 'text', '')
            if offending_symbol is not None
            else ''
        )

        # The placeholder predicate paint of the pre-release syntax.
        if (token_text == ':' and recognizer is not None
                and ParsingError._placeholder_paint(offending_symbol,
                                                    recognizer)):
            return (
                "A predicate paint is written "
                "`nodes[where F(x, y, ...)] = CLASS;`: the condition is an "
                "expression over the coordinates x, y, z. The "
                "form `nodes[F(:, :, ...)] = CLASS;` is not accepted."
            )
        # f.out used as an expression (RHS): grammar only allows f.in there
        if ("'out'" in msg and "'in'" in msg
                and offending_symbol is not None
                and token_text == 'out'):
            return (
                "f.out[...] cannot be used as an expression. "
                "Use f.in[...] to read from the lattice. "
                "f.out[...] may only appear on the left-hand side of "
                "lattice assignment statements (e.g. f.out[x | 0] = expr;)"
            )
        # masked + gauge: user wrote `node_class WALL(Init, Dyn, Gauge) masked;`
        # but the grammar's masked variant has at most 2 args (no gauge).
        if ("'masked'" in msg
                and offending_symbol is not None
                and token_text == 'masked'):
            return (
                "Cannot combine `masked` with a gauge. A masked node "
                "class is skipped at runtime and its output positions "
                "are NaN-filled, so a gauge would never run. The masked "
                "variant takes at most 2 arguments: "
                "`node_class FOO(Init, Dyn) masked;` (or fewer)."
            )
        return msg
