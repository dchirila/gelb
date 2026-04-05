lexer grammar CommonLexerRules;

//                     BEGIN: Keywords                     //
SIMULATION_DESCRIPTION : 'simulation_description' ;
GLOBAL_CONSTANTS : 'global_constants' ;
LATTICES : 'lattices' ;
LATTICE : 'lattice' ;
NODE_CLASSES : 'node_classes' ;
// INITIALIZERS : 'initializers' ;
// DYNAMICS : 'dynamics' ;
// GAUGES : 'gauges' ;

// BEGIN: Keywords for intrinsic functions
SUM : 'sum' ;
DOT_PROD : 'dot_prod' ;
SIN : 'sin' ;
COS : 'cos' ;
SQRT : 'sqrt' ;
RANDOM : 'random' ;
EXP : 'exp' ;
ABS : 'abs' ;
LOG : 'log' ;
TAN : 'tan' ;
TANH : 'tanh' ;
MIN : 'min' ;
MAX : 'max' ;
MOD : 'mod' ;
ATAN2 : 'atan2' ;
UPSTREAM_DFS : 'upstream_dfs' ;
BOUNCE_BACK_DFS : 'bounce_back_dfs' ;
MATMUL : 'matmul' ;
TRANSPOSE : 'transpose' ;
INVERSE : 'inverse' ;
DETERMINANT : 'determinant' ;
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
FUNCTION : 'function' ;

NODE_CLASS : 'node_class' ;
MASKED : 'masked' ;
GEOMETRY : 'geometry' ;
NODES : 'nodes' ;
BORDER : 'border' ;
WHERE : 'where' ;
// Reserved for later language stages (moving geometry).
// None of these is an implemented feature; reserving them keeps v1
// programs from using them as identifiers.
ENTER : 'enter' ;
LEAVE : 'leave' ;
REDUCE : 'reduce' ;
REDUCTION : 'reduction' ;
UPDATE : 'update' ;
GLOBAL_VARIABLES : 'global_variables' ;
TRANSITION : 'transition' ;
ZONE : 'zone' ;
//                     END: Keywords                     //

//                     BEGIN: Operators                     //
ARROW : '->' ;
OP_ASSIGN : '=' ;
OP_ADD : '+' ;
OP_SUB : '-' ;
OP_MUL : '*' ;
OP_DIV : '/' ;
OP_POW : '^' ;
// ... comparison operators
OP_LESS : '<' ;
OP_GREATER : '>' ;
OP_LESS_EQUAL : '<=' ;
OP_GREATER_EQUAL : '>=' ;
OP_EQUAL : '==' ;
OP_NOT_EQUAL : '!=' ;
// ... logical operators
OP_NOT : '!' ; // Currently unused but reserved for future use
OP_AND : '&&' ;
OP_OR : '||' ;
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
VERT : '|' ;  // Reserved: separates spatial coords from DF range in lattice access (see LANGUAGE_DESIGN.md)
COMMA : ',' ;
DOT : '.' ;
//                     END: Punctuation                     //

//                     BEGIN: Scalar literals                     //
// Numbers
// DESIGN DECISION: Both integer and real literals are defined as NON_NEGATIVE only.
// Negative numbers are created using the unary minus operator in the parser.
// This avoids lexer ambiguity (e.g., "x-3" vs "x -3") and follows standard
// compiler design practices used by C, Java, Python, etc.
// Example: -3.14 is parsed as (UnaryMinus (RealLiteral 3.14))
// ... real
NON_NEGATIVE_REAL_LITERAL : [0-9]+ DOT [0-9]* EXPONENT?
                          | DOT [0-9]+ EXPONENT?
                          | NON_NEGATIVE_INT_LITERAL EXPONENT
                          ;
// Helper fragment for real literals
fragment EXPONENT : [Ee] (OP_ADD | OP_SUB)? [0-9]+ ;
// ... int
NON_NEGATIVE_INT_LITERAL : '0' | ( [1-9] [0-9]* ) ;
// ... bool
BOOL_LITERAL : TRUE | FALSE ;
// Helper fragments for boolean literals
fragment TRUE : 'true' ;
fragment FALSE : 'false' ;

 /* STRINGs-rule (valid for {single, multi}-line, double-quoted strings only)
    NOTE: No escape sequences are supported.
    NOTE: Unlike Python (which also allows strings delimited by single-quotes),
          strings in GeLB always use DOUBLE-quotes. Single-quotes can appear
          inside strings without escaping.
          */
STRING_LITERAL : '"' (~["])* '"' ;
//                     END: Scalar literals                     //

// Comments (to IGNORE)
SINGLE_LINE_COMMENT : '//' ~[\r\n]* '\r'? '\n' -> channel(HIDDEN);
MULTI_LINE_COMMENT : '/*' .*? '*/' -> channel(HIDDEN);

// Identifier (i.e. names for user-defined entities)
//
// Examples: f, SetDFsToZero, SetDFsToOne, CurrentState, state, BULK
//
// ATTENTION: always keep this after the keyword rules, to avoid matching language
//            keywords as identifiers!
ID : [a-zA-Z_] [a-zA-Z0-9_]* ;

// Whitespace (to IGNORE)
WS : [ \r\t\u000C\n]+ -> channel(HIDDEN);
