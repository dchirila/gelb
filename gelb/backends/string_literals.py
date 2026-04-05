"""Target-language quoting for metadata and file names (UTF-8)."""


def description_text(node):
    """The parser retains the source string's enclosing double quotes."""
    text = node.value
    return text[1:-1] if text.startswith('"') and text.endswith('"') else text


def cpp_string(text):
    # Fixed-width octal escapes cannot consume a following hex digit, and
    # encode control characters and Unicode identically on every compiler.
    return '"' + ''.join(
        chr(b) if 32 <= b < 127 and b not in (34, 92) else f'\\{b:03o}'
        for b in text.encode('utf-8')) + '"'


def fortran_string(text):
    parts = []
    literal = []
    for char in text:
        if ord(char) < 32 or ord(char) == 127 or char == '\\':
            if literal:
                parts.append("'" + ''.join(literal) + "'")
                literal = []
            parts.append(f'achar({ord(char)})')
        else:
            literal.append("''" if char == "'" else char)
    if literal or not parts:
        parts.append("'" + ''.join(literal) + "'")
    return ' // '.join(parts)
