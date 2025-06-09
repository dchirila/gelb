#!/usr/bin/env python3

import pytest
from gelb.gelb_ast.ASTNodes import *
from gelb.tests.test_utils import (
    get_typed_ast, 
    minimal_gelb_program_1d
)
from gelb.utils.exceptions import GeLBException


class TestStringTypeSeparation:
    """Test that StringType_N is properly separated from computational type system."""
    
    def test_string_literal_structure(self):
        """Test that string literals are created properly in simulation_description."""
        gelb_code = minimal_gelb_program_1d()
        gelb_code = gelb_code.replace('simulation_description("");', 'simulation_description("Test");')
        ast = get_typed_ast(gelb_code)
        
        string_literal = ast.simulation_description
        assert isinstance(string_literal, StringLiteral_N)
        # simulation_description strings don't go through type inference (they're metadata)
        # so they don't have inferred_type attributes
        
    def test_string_type_str_representation(self):
        """Test that StringType_N has correct string representation."""
        string_type = StringType_N(None)
        assert str(string_type) == "(StringType)"
        assert "StringType_N" in repr(string_type)


class TestStringTypeValidation:
    """Test that strings are properly rejected in computational contexts."""
    
    def test_simulation_description_with_string_succeeds(self):
        """Test that strings are allowed in simulation_description."""
        gelb_code = '''
        simulation_description("This should work");
        
        lattices {
            lattice f(1, 1, int, 32, false);
        }
        
        initializer Init {
            f.out[x | 0] = 0;
        }
        
        dynamic Update {
            f.out[x | 0] = 1;  
        }
        
        gauge Output(out = {int state;}) {
            state = f.in[x | 0];
        }
        
        node_classes {
            node_class BULK(Init, Update, Output);
        }
        
        geometry {
            nodes[:] = BULK;
        }
        '''
        # This should not raise an exception
        ast = get_typed_ast(gelb_code)
        assert isinstance(ast.simulation_description, StringLiteral_N)


class TestStringTypeNotInComputationalContexts:
    """Test that strings cannot be used in computational contexts."""
    
    # Note: Since strings are not in the grammar for variable declarations,
    # lattice df_types, etc., these would be parse errors rather than type errors.
    # The type system validation is more of a safeguard against future grammar changes.
    
    def test_string_type_conceptual_separation(self):
        """Test that StringType_N is conceptually separate from computational types."""
        string_type = StringType_N(None)
        array_type = ArrayDataType_N(None, "int", List_N(None))
        
        # StringType_N should not be an ArrayDataType_N (the only computational type)
        assert not isinstance(string_type, ArrayDataType_N)
        assert isinstance(array_type, ArrayDataType_N)
        
        # StringType_N should have no children (terminal node)
        assert string_type.get_children() == set()