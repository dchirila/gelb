lexer grammar CommonLexerRules;

// GeLB Keywords
GELB_VERSION: 'gelb_version';
LATTICES: 'lattices';
LATTICE: 'lattice';

INT: 'int';
BOOL: 'bool';
TRUE: 'true';
FALSE: 'false';

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
