#!/usr/bin/env python3

from gelb.utils.exceptions import *

class SymbolDefinition:
    """
    Container for a single symbol in a GeLB program.

    Each Symbols has the following attributes:
    - name
    - tag
    - value
    """
    def __init__(self, name, tag, value):
        self.name = name
        self.tag = tag
        self.value = value

    def __repr__(self):
        """Terse representation (for unit-testing)."""
        return (
            f"(Symbol (Name \"{self.name}\")"
            f" (Tag \"{self.tag}\")"
            f" (Value {self.value}))"
        )

