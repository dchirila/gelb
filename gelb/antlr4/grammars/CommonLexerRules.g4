lexer grammar CommonLexerRules;

// BEGIN: GeLB Keywords //

GELB_VERSION: 'gelb_version';
LATTICES: 'lattices';
LATTICE: 'lattice';

// // BEGIN: Keywords for intrinsic GeLB functions // //
DOT_PRODUCT : 'dot_product' ;
VEC_PRODUCT : 'vector_product' ;
UP_STREAM_DF : 'up_stream_df' ;
DOWN_STREAM_DF : 'down_stream_df' ;
OPPOSITE_DF : 'opposite_df' ;
// // END: Keywords for intrinsic GeLB functions // //

// // BEGIN: Keywords for GeLB data-types // //
INT: 'int';
BOOL: 'bool';
TRUE: 'true';
FALSE: 'false';
// // END: Keywords for GeLB data-types // //

INITIALIZER: 'initializer';
OUT: 'out';
IN: 'in';
X: 'x';
Y: 'y';
Z: 'z';

CONST: 'const';

SIZE: 'size';
PERIODICITY: 'periodicity';

NODE_CLASSES: 'node_classes';
INITIALIZERS: 'initializers';
DYNAMICS: 'dynamics';
GAUGES: 'gauges';

DYNAMIC: 'dynamic';
GAUGE: 'gauge';

NODE_CLASS: 'node_class';
GEOMETRY: 'geometry';
NODES: 'nodes';
// END: GeLB Keywords //

// Operators
OP_ASSIGN: '=';
// ... chevrons (angle brackets)
OP_LESS: '<';
OP_GREATER: '>';

// parentheses
PAREN_OPEN: '(';
PAREN_CLOSE: ')';
// square brackets
BRACKET_OPEN: '[';
BRACKET_CLOSE: ']';
// curly brackets
CURLY_OPEN: '{';
CURLY_CLOSE: '}';

// MISC Symbols (punctuation, etc.)
COLON: ':';
SEMICOLON: ';';
VERT: '|';
COMMA: ',';
DOT: '.';

// Identifier (i.e. names for user-defined entities)
// ID : LETTER (LETTER | DIGIT | '_')* ;

// Literals
INT_LITERAL: '0' | [1-9][0-9]* ;

// Numbers
// ... int
NON_NEGATIVE_INTEGER: DIGIT+ ;
fragment DIGIT: [0-9] ;

// fragment LETTER : [a-zA-Z] ;

/* STRINGs-rule (valid for {single, multi}-line strings) NOTE: to simplify things, we only allow
 strings marked by DOUBLE-quotes (unlike Python, which also allows strings marked by SINGLE-quotes)
 */
// STRING : '"' (~[\\"] | '\\' [\\"()])* '"' ;

// // Comments (to IGNORE)

// SINGLE_LINE_COMMENT : '//' ~[\r\n]* '\r'? '\n' -> channel(HIDDEN);

// MULTI_LINE_COMMENT : '/*' .*? '*/' -> channel(HIDDEN);

// Whitespace (to IGNORE)
WS: [ \r\t\u000C\n]+ -> channel(HIDDEN);


// **** TMP **** //

// CONFIGURATION : 'configuration' ;
// SIMULATION_METADATA : 'simulation_metadata' ;
// SHORT_NAME : 'short_name' ;
// DESCRIPTION : 'description' ;
// CONSTANTS : 'constants' ;
// CONST : 'const' ;
// ARRAY : 'array' ;
// LATTICE_PROPERTIES : 'lattice_properties' ;

// // Operators
OP_ASSIGN : '=' ;
// OP_LT : '<' ;
// OP_GT : '>' ;

// // Supported scalar data-types
// // // bool
// BOOL : 'bool' ;
// // // int
// INT64 : 'int64' ;
// INT32 : 'int32' ;
// INT16 : 'int16' ;
// INT8 : 'int8' ;
// INT : 'int' ;
// // // real
// REAL64 : 'real64' ;
// REAL32 : 'real32' ;
// REAL16 : 'real16' ;
// REAL : 'real' ;

// // MISC Symbols (punctuation, etc.)
SEMICOLON : ';' ;
// COLON     : ':' ;
// COMMA     : ',' ;
// DOT       : '.' ;
// VERT      : '|' ;

// // Parentheses
// LCURLY : '{' ;
// RCURLY : '}' ;

// fragment LETTER : [a-zA-Z] ;

// ID : LETTER (LETTER | DIGIT | '_')* ;

// // Numbers
NON_NEGATIVE_INT : NON_ZERO_DIGIT DIGIT* ;
DIGIT : ZERO_DIGIT | NON_ZERO_DIGIT ;
fragment NON_ZERO_DIGIT : '1'..'9' ;
fragment ZERO_DIGIT : '0' ;

 /* STRINGs-rule (valid for {single, multi}-line strings)
    NOTE: to simplify things, we only allow strings marked by DOUBLE-quotes
          (unlike Python, which also allows strings marked by SINGLE-quotes) */
// STRING : '"' (~[\\"] | '\\' [\\"()])* '"' ;

// // Comments (to IGNORE)
// SINGLE_LINE_COMMENT : '//' ~[\r\n]* '\r'? '\n' -> channel(HIDDEN);
// MULTI_LINE_COMMENT : '/*' .*? '*/' -> channel(HIDDEN);

// Whitespace (to IGNORE)
WS : [ \r\t\u000C\n]+ -> channel(HIDDEN);