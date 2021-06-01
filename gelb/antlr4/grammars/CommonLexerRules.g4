lexer grammar CommonLexerRules;

//                     BEGIN: Keywords                     //
SIMULATION_NAME : 'simulation_name' ;
SIMULATION_DESCRIPTION : 'simulation_description' ;
GLOBAL_CONSTANTS : 'global_constants' ;
LATTICES : 'lattices' ;
LATTICE : 'lattice' ;
LATTICE_CONSTANTS : 'lattice_constants' ;
NODE_CLASSES : 'node_classes' ;
// INITIALIZERS : 'initializers' ;
// DYNAMICS : 'dynamics' ;
// GAUGES : 'gauges' ;

// BEGIN: Keywords for intrinsic functions
// DOT_PRODUCT : 'dot_product' ;
// VEC_PRODUCT : 'vector_product' ;
// UP_STREAM_DF : 'up_stream_df' ;
// DOWN_STREAM_DF : 'down_stream_df' ;
// OPPOSITE_DF : 'opposite_df' ;
// END: Keywords for intrinsic functions

// BEGIN: Keywords for data-types
// bool
BOOL : 'bool' ;
// int
INT64 : 'int64' ;
INT32 : 'int32' ;
INT16 : 'int16' ;
INT8 : 'int8' ;
INT : 'int' ;
// real
REAL64 : 'real64' ;
REAL32 : 'real32' ;
REAL16 : 'real16' ;
REAL : 'real' ;
// datatype-modifiers (for constants and arrays)
CONST : 'const' ;
ARRAY : 'array' ;
// END: Keywords for data-types

INITIALIZER: 'initializer';
OUT : 'out' ;
IN : 'in' ;

// SIZE : 'size' ;
// PERIODICITY : 'periodicity' ;


DYNAMIC : 'dynamic' ;
GAUGE : 'gauge' ;

NODE_CLASS : 'node_class' ;
GEOMETRY : 'geometry' ;
NODES : 'nodes' ;
//                     END: Keywords                     //

//                     BEGIN: Operators                     //
OP_ASSIGN : '=' ;
OP_ADD : '+' ;
OP_SUB : '-' ;
OP_MUL : '*' ;
OP_DIV : '/' ;
OP_POW : '^' ;
// ... chevrons (angle brackets)
OP_LESS : '<' ;
OP_GREATER : '>' ;
// ... logical operators
OP_NOT : '!' ;
//                     END: Operators                     //

//                     BEGIN: Punctuation                     //
// parentheses
PAREN_OPEN : '(' ;
PAREN_CLOSE : ')' ;
// square brackets
BRACKET_OPEN : '[' ;
BRACKET_CLOSE : ']' ;
// curly brackets
CURLY_OPEN : '{' ;
CURLY_CLOSE : '}' ;
// MISC Symbols
COLON: ':';
SEMICOLON : ';' ;
VERT : '|' ;
COMMA : ',' ;
DOT : '.' ;
//                     END: Punctuation                     //

//                     BEGIN: Scalar literals                     //
// Numbers
// ... real
NON_NEGATIVE_REAL_LITERAL : [0-9]+ DOT [0-9]* EXPONENT?
                          | DOT [0-9]+ EXPONENT?
                          | NON_NEGATIVE_INT_LITERAL EXPONENT
                          ;
EXPONENT : [Ee] (OP_ADD | OP_SUB)? [0-9]+ ;
// ... int
NON_NEGATIVE_INT_LITERAL : '0' | ( [1-9] [0-9]* ) ;
// ... bool
BOOL_LITERAL : TRUE | FALSE ;
TRUE : 'true' ;
FALSE : 'false' ;

 /* STRINGs-rule (valid for {single, multi}-line strings)
    NOTE: to simplify things, we only allow strings marked by DOUBLE-quotes
          (unlike Python, which also allows strings marked by SINGLE-quotes) */
STRING : '"' (~[\\"] | '\\' [\\"()])* '"' ;
//                     END: Scalar literals                     //

// Comments (to IGNORE)
SINGLE_LINE_COMMENT : '//' ~[\r\n]* '\r'? '\n' -> channel(HIDDEN);
MULTI_LINE_COMMENT : '/*' .*? '*/' -> channel(HIDDEN);

// Identifier (i.e. names for user-defined entities)
// Examples: f, SetDFsToZero, SetDFsToOne, CurrentState, state, BULK
ID : [a-zA-Z_] [a-zA-Z0-9_]* ;

// Whitespace (to IGNORE)
WS : [ \r\t\u000C\n]+ -> channel(HIDDEN);
