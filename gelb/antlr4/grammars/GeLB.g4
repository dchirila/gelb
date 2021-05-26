grammar GeLB;
import CommonLexerRules;

gelb_program : //
	set_simulation_name_stmt
	set_simulation_description_stmt
	global_constants_block
	lattices_block
	// initializer_block //
	// dynamic_block
	// gauge_block
	// function_block
	// node_classes_block
	// geometry_block
	EOF;

set_simulation_name_stmt : SIMULATION_NAME PAREN_OPEN
    STRING
PAREN_CLOSE SEMICOLON;

set_simulation_description_stmt : SIMULATION_DESCRIPTION PAREN_OPEN
    STRING
PAREN_CLOSE SEMICOLON;

lattice_properties_sub_block : LATTICE_PROPERTIES ID CURLY_OPEN
    constant_definition_stmt*
CURLY_CLOSE;

lattices_block : LATTICES CURLY_OPEN
    // NOTE: a program needs at least one lattice!
	TODO // lattice_instantiation_stmt+
CURLY_CLOSE;

// lattice_instantiation: //
// 	LATTICE ID PAREN_OPEN //
// 	NON_NEGATIVE_INTEGER // d
// 	COMMA //
// 	NON_NEGATIVE_INTEGER // q
// 	COMMA //
// 	INT // df_type
// 	COMMA //
// 	CURLY_OPEN NON_NEGATIVE_INTEGER CURLY_CLOSE // size
// 	COMMA //
// 	CURLY_OPEN FALSE CURLY_CLOSE // periodicity
// 	PAREN_CLOSE SEMICOLON;

// initializer_block: //
// 	INITIALIZER ID CURLY_OPEN //
// 	lattice_assignment_stmt //
// 	CURLY_CLOSE;

// lattice_assignment_stmt: //
// 	dfs_selection //
// 	OP_ASSIGN //
// 	NON_NEGATIVE_INTEGER //
// 	SEMICOLON;

// dfs_selection: //
// 	ID DOT OUT //
// 	BRACKET_OPEN //
// 	X VERT NON_NEGATIVE_INTEGER //
// 	BRACKET_CLOSE;

global_constants_block: GLOBAL_CONSTANTS CURLY_OPEN
    constant_definition_stmt*
CURLY_CLOSE ;

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
       - a scalar_expr (for dimensionality == 1)
     */
    (array_literal_1d | scalar_expr)
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
    scalar_expr (COMMA scalar_expr)+
CURLY_CLOSE ;

variable_assignment_stmt : ID OP_ASSIGN scalar_expr SEMICOLON ;

/* TODO:
   - allow simple arithmetic expressions
   - allow expressions involving built-in functions (which can be evaluated
   statically) and scalar-valued array expressions -- basically, as long as the
   result is a scalar, we should accept it here.
 */
scalar_expr : NON_NEGATIVE_INTEGER ;