#!/usr/bin/env python3

from gelb.utils.exceptions import *

class SymbolsTable:
    """
    Container for symbols tables in GeLB.

    The table is stored as a list-of-dictionaries, where each dictionary
    contains three entries:
    - name
    - type
    - value
    """
    def __init__(self):
        self.lod = []

    def add_symbol(self, curr_instance):
        # guard against appending a symbol twice
        already_present, prev_instance = self.symbol_already_present(
            curr_instance['name']
        )
        if already_present:
            raise GeLBExSymbolExists(curr_instance, prev_instance)
        self.lod.append(curr_instance)

    def symbol_already_present(self, symbol_name):
        if self.lod:  # lod is not empty
            for d in self.lod:
                if str(d['name']) == symbol_name:
                    return True, d
        return False, None

    def __str__(self):
        """Pretty-printed representation (in table format)."""
        result =  f"{'name'.ljust(20)}|{'type'.ljust(20)}| value\n"
        result += f"{'-'*20}|{'-'*20}|{'-'*40}\n"
        for d in self.lod:
            result += (
                f"{str(d['name']).ljust(20)}|"
                f"{str(d['type']).ljust(20)}|"
                f" {d['value']}\n"
            )
        return result

    def __repr__(self):
        """Terse representation (for unit-testing)."""
        result = ""
        for d in self.lod:
            if result != "":  # add a space (but not for 1st instance)
                result += " "
            result += f"({str(d['name'])} \"{str(d['type'])}\" {d['value']})"
        return result




