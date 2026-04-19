#!/usr/bin/env python3
"""
Validation test utilities.

This module provides utilities specific to AST validation and error checking tests.
"""

def get_constants_resolution_test_data():
    """Return test data for constant resolution validation tests."""
    return [
        # Valid constant resolutions
        ("simple_constant", 
         """
         global_constants {
           const int N = 32;
           const int DOUBLED = N * 2;
         }
         """,
         "DOUBLED", 64),
        
        ("arithmetic_expression",
         """
         global_constants {
           const int A = 10;
           const int B = 5;
           const int SUM = A + B;
           const int PRODUCT = A * B;
         }
         """,
         "PRODUCT", 50),
        
        ("real_constants",
         """
         global_constants {
           const real PI = 3.14159;
           const real TAU = PI * 2;
         }
         """,
         "TAU", 6.28318),
        
        ("boolean_constants",
         """
         global_constants {
           const bool FLAG1 = true;
           const bool FLAG2 = false;
           const bool COMBINED = FLAG1 && FLAG2;
         }
         """,
         "COMBINED", False),
        
        # Complex expressions with multiple dependencies
        ("complex_expression",
         """
         global_constants {
           const int BASE = 5;
           const int MULTIPLIER = 3;
           const int OFFSET = 2;
           const int RESULT = BASE * MULTIPLIER + OFFSET;
         }
         """,
         "RESULT", 17),
    ]


def get_range_resolver_test_data():
    """Return test data for range resolution validation tests."""
    return [
        # Simple range tests
        ("simple_start_stop", "1:5", "Range_N(start=IntLiteral_N(value=1), stop=IntLiteral_N(value=5), step=IntLiteral_N(value=1))"),
        ("with_step", "0:10:2", "Range_N(start=IntLiteral_N(value=0), stop=IntLiteral_N(value=10), step=IntLiteral_N(value=2))"),
        ("negative_step", "10:0:-1", "Range_N(start=IntLiteral_N(value=10), stop=IntLiteral_N(value=0), step=IntLiteral_N(value=-1))"),
        
        # Range with expressions
        ("expression_start", "N-1:N+1", "Range_N(start=Sub_N(left=Identifier_N(name='N'), right=IntLiteral_N(value=1)), stop=Add_N(left=Identifier_N(name='N'), right=IntLiteral_N(value=1)), step=IntLiteral_N(value=1))"),
        ("expression_step", "0:10:N/2", "Range_N(start=IntLiteral_N(value=0), stop=IntLiteral_N(value=10), step=Div_N(left=Identifier_N(name='N'), right=IntLiteral_N(value=2)))"),
        
        # Coordinate range tests  
        ("coordinate_range_1d", "x", "CoordsRange_N(start=Identifier_N(name='x'), stop=Identifier_N(name='x'), step=IntLiteral_N(value=1))"),
        ("coordinate_range_2d", "x,y", "CoordsList_N(elements=[CoordsRange_N(start=Identifier_N(name='x'), stop=Identifier_N(name='x'), step=IntLiteral_N(value=1)), CoordsRange_N(start=Identifier_N(name='y'), stop=Identifier_N(name='y'), step=IntLiteral_N(value=1))])"),
        ("coordinate_range_with_colon", "x:x+1", "CoordsRange_N(start=Identifier_N(name='x'), stop=Add_N(left=Identifier_N(name='x'), right=IntLiteral_N(value=1)), step=IntLiteral_N(value=1))"),
        
        # DF range tests
        ("df_range_simple", "0", "IntLiteral_N(value=0)"),
        ("df_range_colon", "0:2", "Range_N(start=IntLiteral_N(value=0), stop=IntLiteral_N(value=2), step=IntLiteral_N(value=1))"),
        ("df_range_all", ":", "Range_N(start=IntLiteral_N(value=0), stop=Identifier_N(name='Q'), step=IntLiteral_N(value=1))"),
    ]


def get_implicit_symbols_test_data():
    """Return test data for implicit symbols validation tests."""
    return [
        # Valid uses of implicit symbols
        ("initializer_x_allowed", "initializer",
         """
         initializer init_fun1 {
           f.out[x | 0] = 1.0;
         }
         """, True),
        
        ("dynamic_xy_allowed", "dynamic", 
         """
         dynamic dyn_fun1 {
           f.out[x, y | 0] = f.in[x, y | 0];
         }
         """, True),
        
        ("gauge_xyz_allowed", "gauge",
         """
         gauge gauge_fun1 -> (real rho) {
           rho = f.in[x, y, z | 0];
         }
         """, True),
        
        # Invalid uses of implicit symbols
        ("global_constants_x_forbidden", "global_constants",
         """
         global_constants {
           const int INVALID = x;
         }
         """, False),
        
        ("lattices_dimension_forbidden", "lattices",
         """
         lattices {
           lattice myLattice(x, 5, int, 32, false);
         }
         """, False),
        
        ("node_classes_forbidden", "node_classes",
         """
         node_classes {
           node_class my_node_class(x, dyn_fun1, gauge_fun1);
         }
         """, False),
        
        ("geometry_forbidden", "geometry",
         """
         geometry {
           nodes[x] = BULK;
         }
         """, False),
    ]