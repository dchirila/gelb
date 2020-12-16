lexer grammar CommonLexerRules;

// // GD Keywords
// DOT_PRODUCT : 'DotProduct' ;
// VEC_PRODUCT : 'VectorProduct' ;
// UP_STREAM_DF : 'UpStreamDF' ;
// DOWN_STREAM_DF : 'DownStreamDF' ;
// OPPOSITE_DF : 'OppositeDF' ;

GD_VERSION : 'gd_version' ;
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

// /* STRINGs-rule (valid for {single, multi}-line strings)
//    NOTE: to simplify things, we only allow strings marked by DOUBLE-quotes
//          (unlike Python, which also allows strings marked by SINGLE-quotes) */
// STRING : '"' (~[\\"] | '\\' [\\"()])* '"' ;

// // Comments (to IGNORE)
// SINGLE_LINE_COMMENT : '//' ~[\r\n]* '\r'? '\n' -> channel(HIDDEN);
// MULTI_LINE_COMMENT : '/*' .*? '*/' -> channel(HIDDEN);

// Whitespace (to IGNORE)
WS : [ \r\t\u000C\n]+ -> channel(HIDDEN);
