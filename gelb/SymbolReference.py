#!/usr/bin/env python3


class SymbolReference:
    """
    Container for a single symbol reference in a GeLB program.
    """
    def __init__(self, name, code_range):
        self.name = name
        self.code_range = code_range

    def __repr__(self):
        """Terese representation (for unit-testing)."""
        return (
            f"(SymbolReference"
            f" (Name \"{self.name}\")"
            f" (CodeRange {self.code_range}))"
        )
