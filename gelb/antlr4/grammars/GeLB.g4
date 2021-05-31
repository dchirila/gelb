grammar GeLB;
import CommonLexerRules;

gelb_program : //
	set_simulation_name_stmt
	set_simulation_description_stmt
	global_constants_block?  // 0 or 1 instance
	lattice_constants_block*  // 0 or more instance(s)
	lattices_block
	// initializer_block //
	// dynamic_block
	// gauge_block
	// function_block
	// node_classes_block
	// geometry_block  // TODO add periodicity here
	EOF;

set_simulation_name_stmt : SIMULATION_NAME PAREN_OPEN
    STRING
PAREN_CLOSE SEMICOLON;

set_simulation_description_stmt : SIMULATION_DESCRIPTION PAREN_OPEN
    STRING
PAREN_CLOSE SEMICOLON;

// When this optional block is present...
global_constants_block: GLOBAL_CONSTANTS CURLY_OPEN
    // it should contain at least one constant definition
    constant_definition_stmt+
CURLY_CLOSE ;

// When this optional block is present...
lattice_constants_block : LATTICE_CONSTANTS identifier CURLY_OPEN
    // it should contain at least one constant definition
    constant_definition_stmt+
CURLY_CLOSE;

lattices_block : LATTICES CURLY_OPEN
    // NOTE: a program needs at least one lattice!
	lattice_insta_stmt+
CURLY_CLOSE;

 lattice_insta_stmt :                   // Example:
    LATTICE identifier PAREN_OPEN       // lattice f(
 	NON_NEGATIVE_INTEGER COMMA          //   d=2,
 	NON_NEGATIVE_INTEGER COMMA          //   q=9,
 	scalar_data_type COMMA              //   df_type=int64,
 	lattice_size                        //   size=256
 	PAREN_CLOSE SEMICOLON;              // );

lattice_size : array_literal_1d
             | NON_NEGATIVE_INTEGER ;

// initializer_block: //
// 	INITIALIZER identifier CURLY_OPEN //
// 	lattice_assignment_stmt //
// 	CURLY_CLOSE;

// lattice_assignment_stmt: //
// 	dfs_selection //
// 	OP_ASSIGN //
// 	NON_NEGATIVE_INTEGER //
// 	SEMICOLON;

// dfs_selection: //
// 	identifier DOT OUT //
// 	BRACKET_OPEN //
// 	X VERT NON_NEGATIVE_INTEGER //
// 	BRACKET_CLOSE;

constant_definition_stmt : CONST data_type variable_assignment_stmt ;

data_type : scalar_data_type
          | array_data_type ;

scalar_data_type : scalar_bool_data_type
                 | scalar_int_data_type
                 | scalar_real_data_type ;

scalar_bool_data_type : BOOL ;
scalar_int_data_type  : INT64 | INT32 | INT16 | INT8 | INT ;
scalar_real_data_type : REAL64 | REAL32 | REAL16 | REAL ;

/*
 NOTE: When we declare one-dimensional arrays, the integer specifying the
 shape (length) should NOT be surrounded by curly braces (because it is a
 scalar, and GeLB tries to be consistent with its rule of always preferring
 the lower-dimensional data-type that does the job.
*/
array_data_type : ARRAY OP_LESS
    scalar_data_type
    COMMA
    /* shape is (depending on dimensionality):
       - a one-dimensional array (for dimensionality >= 2) or
       - a expr (for dimensionality == 1)
     */
    (array_literal_1d | expr)
OP_GREATER ;

/* Fixed-dimensionality array literals
   REFs: - Sec 2.4 @A4-book
         - Ch 4 (A quick tour) & Ch 5 (Designing grammars) @A4-book
         - py3antlr4book repo
   NOTE: the '+' sign for the repetitions. Basically, this forbids:
   - one-dimensional array literals which are just scalars,
   - two-dimensional array literals which are just one-dimensional arrays,
   - etc.
   The rule is that, if you can use a lower-dimensionality data-type, you
   should do so (because the program author has to specify less indices, and
   the code also become easier to understand).
 */
array_literal_4d : CURLY_OPEN
    array_literal_3d (COMMA array_literal_3d)+
CURLY_CLOSE ;

array_literal_3d : CURLY_OPEN
    array_literal_2d (COMMA array_literal_2d)+
CURLY_CLOSE ;

array_literal_2d : CURLY_OPEN
    array_literal_1d (COMMA array_literal_1d)+
CURLY_CLOSE ;

array_literal_1d : CURLY_OPEN
    expr (COMMA expr)+
CURLY_CLOSE ;

variable_assignment_stmt : identifier OP_ASSIGN
    expr
SEMICOLON ;

identifier : ID ;

/* TODO:
   - allow simple arithmetic expressions
   - allow expressions involving built-in functions (which can be evaluated
   statically) and scalar-valued array expressions -- basically, as long as the
   result is a scalar, we should accept it here.
 */
expr : PAREN_OPEN expr PAREN_CLOSE         # parensExpr
     | op=(OP_ADD | OP_SUB | OP_NOT) expr  # unaryExpr
     | value=NON_NEGATIVE_INTEGER          # nonNegIntExpr
     ;

//expr : PAREN_OPEN expr PAREN_CLOSE               # parensExpr
//     | op=(OP_ADD | OP_SUB) expr                 # unaryExpr
//     | left=expr op=(OP_MUL | OP_DIV) right=expr # infixBinaryExpr
//     | left=expr op=(OP_ADD | OP_SUB) right=expr # infixBinaryExpr
//     // BEGIN :: literals //
//     | NON_NEGATIVE_INTEGER                   # intLiteralExpr
//     | NON_NEGATIVE_REAL                      # realLiteralExpr
//     | TRUE                          # boolLiteralExpr
//     | FALSE                         # boolLiteralExpr
//     | array_literal_4d # arrayLiteralExpr
//     | array_literal_3d # arrayLiteralExpr
//     | array_literal_2d # arrayLiteralExpr
//     | array_literal_1d # arrayLiteralExpr
//     // END :: literals //
//     ;