#!/usr/bin/env python3

from gelb.utils.exceptions import (
    GeLBExSymbolExists
)


class SymbolsTable:
    """
    Container for symbol_defs tables in GeLB.

    The table is stored as a list of SymbolDefinition instances.
    """
    def __init__(self):
        self.symbol_defs = []

    def __getitem__(self, item):
        return self.symbol_defs[item]

    def __iter__(self):
        # return an iterator over the symbol_defs list
        return iter(self.symbol_defs)

    def __len__(self):
        return len(self.symbol_defs)

    def __setitem__(self, key, value):
        self.symbol_defs[key] = value

    def append(self, curr_instance):
        # guard against appending a symbol twice
        if self.contains(curr_instance.name):
            raise GeLBExSymbolExists(
                curr_instance,
                self.get_symbol_definition(curr_instance.name)
            )
        return self.symbol_defs.append(curr_instance)

    def contains(self, symbol_name):
        if self.symbol_defs:  # symbol_defs list is not empty
            for sdef in self.symbol_defs:
                if str(sdef.name) == symbol_name:
                    return True
        return False

    def get_symbol_definition(self, symbol_name):
        if self.symbol_defs:  # symbol_defs list is not empty
            for sdef in self.symbol_defs:
                if str(sdef.name) == symbol_name:
                    return sdef
        return None

    def __str__(self):
        """Pretty-printed representation (in table format)."""
        result = f"{'name'.ljust(30)}|{'tag'.ljust(30)}| value\n"
        result += f"{'-'*30}|{'-'*30}|{'-'*40}\n"
        for s in self.symbol_defs:
            result += (
                f"{str(s.name.ljust(30))}|"
                f"{str(s.tag.ljust(30))}|"
                f" {s.value}\n"
            )
        return result

    def __repr__(self):
        """Terse representation (for unit-testing)."""
        result = ""
        for sdef in self.symbol_defs:
            if result != "":  # add a space (but not for 1st instance)
                result += " "
            result += f"({str(sdef.name)} \"{str(sdef.tag)}\" {sdef.value})"
        return result
