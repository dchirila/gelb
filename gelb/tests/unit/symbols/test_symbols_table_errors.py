#!/usr/bin/env python3

import pytest
from gelb.tests.unit.symbols.symbol_test_utils import get_symbol_table_error_test_data, get_symbol_table_valid_test_data
from gelb.tests.test_utils import get_ast
from gelb.frontend.stage1_frontend import build_symbols_tables


class TestSymbolTableErrors:
    """Consolidated tests for symbol table error validation across all block types."""
    
    @pytest.mark.parametrize("rule,test_name,exception_class,test_string,symbol_to_ignore", get_symbol_table_error_test_data())
    def test_symbol_table_error(self, rule, test_name, exception_class, test_string, symbol_to_ignore):
        """Test that appropriate symbol table exceptions are raised for invalid code."""
        ast = get_ast(rule, test_string)
        
        with pytest.raises(exception_class):
            if symbol_to_ignore:
                build_symbols_tables(ast, symbol_to_ignore)
            else:
                build_symbols_tables(ast)


class TestSymbolTableValid:
    """Consolidated tests for valid symbol table construction across all block types."""
    
    @pytest.mark.parametrize("rule,test_string,symbol_to_ignore,expected_repr", get_symbol_table_valid_test_data())
    def test_symbol_table_valid(self, rule, test_string, symbol_to_ignore, expected_repr):
        """Test that valid symbol table construction works correctly."""
        ast = get_ast(rule, test_string)
        
        if symbol_to_ignore:
            ast = build_symbols_tables(ast, symbol_to_ignore_for_testing=symbol_to_ignore)
        else:
            ast = build_symbols_tables(ast)
            
        assert repr(ast.symbol_defs) == expected_repr