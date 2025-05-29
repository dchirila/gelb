grammar GeLB;
import CommonLexerRules;

/*
 Root grammar rule, for an entire GeLB program.

 NOTE: We want to allow users to specify the block in any order they like.
       To achieve this, we use the pattern:
       gelb_program : ( block_type1 | block_type 2 | ... )* ;

       Later, in ASTBuilderVisitor.visitGelb_program, we enforce some rules,
       e.g. that the number of occurrences of each block-type is valid.
 */
gelb_program : // Valid # of occurrences (as interval)
	( set_simulation_description_stmt  // [1, 1]
	| global_constants_block           // [0, 1]
	| lattices_block                   // [1. 1]
    | initializer_block                // [1, oo)
	| dynamic_block                    // [1, oo)
	| gauge_block                      // [1, oo)
	//| function_block                   // [0, oo)
	| node_classes_block               // [1, 1]
	| geometry_block                   // [1, 1]
	)*
	EOF ;

set_simulation_description_stmt : SIMULATION_DESCRIPTION PAREN_OPEN
    STRING
PAREN_CLOSE SEMICOLON ;

// When this optional block is present...
global_constants_block: GLOBAL_CONSTANTS CURLY_OPEN
    // it should contain at least one constant definition
    constant_definition_stmt+
CURLY_CLOSE ;

lattices_block : LATTICES CURLY_OPEN
    // NOTE: a program needs at least one lattice!
	lattice_insta_stmt+
CURLY_CLOSE ;

lattice_insta_stmt :                   // Example:
    LATTICE identifier PAREN_OPEN        // lattice f(
 	expr                                 //   d=2,
 	COMMA expr                           //   q=9,
 	COMMA scalar_data_type               //   df_type=int64,
 	PAREN_CLOSE SEMICOLON ;              // );

// TODO
block_stmt : constant_definition_stmt
           | variable_declaration_stmt
           // BEGIN :: assignment stmts //
           | lattice_out_selection_assignment_stmt
           | variable_assignment_stmt
//           | array_selection_assignment_stmt
           // END :: assignment stmts //
           ;

initializer_block :
    INITIALIZER identifier CURLY_OPEN
 	block_stmt+
 	CURLY_CLOSE ;

dynamic_block :
    DYNAMIC identifier CURLY_OPEN
 	block_stmt+
    CURLY_CLOSE ;

gauge_block :
    GAUGE identifier
    // BEGIN :: Interface //
    PAREN_OPEN                    // (
    // Gauges only have outputs
    OUT OP_ASSIGN CURLY_OPEN      // out = {
    variable_declaration_stmt+    // int x1; array<real64, 3> x2;
    CURLY_CLOSE PAREN_CLOSE       // })
    // END :: Interface //
    CURLY_OPEN
    block_stmt+  // core statements
    CURLY_CLOSE ;

node_classes_block : NODE_CLASSES CURLY_OPEN  // node_classes {
    node_class_insta_stmt+  // node_class BULK(SetDFsToZero, IncrementDFs, CurrentState)
    CURLY_CLOSE ;                             // }

node_class_insta_stmt : NODE_CLASS
    identifier PAREN_OPEN  // name of the NodeClass
    identifier             // Initializer
    COMMA identifier       // Dynamic
    COMMA identifier       // Gauge
    PAREN_CLOSE SEMICOLON ;

geometry_block : GEOMETRY CURLY_OPEN
    set_grid_size_stmt
    set_grid_periodicity_stmt
    paint_nodes_stmt+
    CURLY_CLOSE ;

set_grid_size_stmt : SET_GRID_SIZE PAREN_OPEN
    expr
    PAREN_CLOSE SEMICOLON ;

set_grid_periodicity_stmt : SET_GRID_PERIODICITY PAREN_OPEN
    expr
    PAREN_CLOSE SEMICOLON ;

paint_nodes_stmt : NODES BRACKET_OPEN  // nodes[
    coords_range (COMMA coords_range)*
    BRACKET_CLOSE OP_ASSIGN           // ] =
    identifier SEMICOLON ;            // BULK ;

lattice_out_selection_assignment_stmt :
    rect_sel_of_lattice_out_dfs
    OP_ASSIGN
    expr
    SEMICOLON ;

rect_sel_of_lattice_out_dfs:
    identifier DOT OUT
    BRACKET_OPEN
    coords_range (COMMA coords_range)*  // spatial ranges
    lattice_dfs_range
    BRACKET_CLOSE ;

rect_sel_of_lattice_in_dfs:
    identifier DOT IN
    BRACKET_OPEN
    coords_range (COMMA coords_range)*  // spatial ranges
    lattice_dfs_range
    BRACKET_CLOSE ;

rect_sel_of_array_elems :
    identifier BRACKET_OPEN
    coords_range (COMMA coords_range)*
    BRACKET_CLOSE ;

/*
 NOTE: Because we use =coords_range= for both spatial- and DFs-selections,
       we define this intermediate rule =lattice_dfs_ranges= to include
       the =VERT= separator. This simplifies processing later.
 */
lattice_dfs_range : VERT coords_range ;

coords_range : low=expr                  # singleElementRange
             | low=expr COLON high=expr  # lowhighBoundRange
             | low=expr COLON            # lowBoundRange
             |          COLON high=expr  # highBoundRange
             |          COLON            # allElementsRange
             ;

constant_definition_stmt : CONST data_type variable_assignment_stmt ;

variable_declaration_stmt : data_type identifier SEMICOLON ;

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
array_data_type : ARRAY BRACKET_OPEN
    scalar_data_type
    COMMA
    /* shape is (depending on dimensionality):
       - a one-dimensional array (for dimensionality >= 2) or
       - a expr (for dimensionality == 1)
     */
    (array_literal_1d | expr)
BRACKET_CLOSE ;

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
   - allow expressions involving built-in functions
   - allow expressions involving user-defined functions
 */
expr : PAREN_OPEN expr PAREN_CLOSE                # parensExpr
     | <assoc=right> left=expr OP_POW right=expr  # powExpr
     | op=(OP_ADD | OP_SUB | OP_NOT) expr         # unaryExpr
     | left=expr op=(OP_MUL | OP_DIV) right=expr  # infixExpr
     | left=expr op=(OP_ADD | OP_SUB) right=expr  # infixExpr
     | left=expr op=(OP_LESS | OP_GREATER | OP_LESS_EQUAL | OP_GREATER_EQUAL) right=expr  # comparisonExpr
     | left=expr op=(OP_EQUAL | OP_NOT_EQUAL) right=expr  # equalityExpr
     | left=expr OP_AND right=expr                 # logicalAndExpr
     | left=expr OP_OR right=expr                  # logicalOrExpr
     // BEGIN :: literals //
     | value=NON_NEGATIVE_REAL_LITERAL     # nonNegRealLiteralExpr
     | value=NON_NEGATIVE_INT_LITERAL      # nonNegIntLiteralExpr
     | value=BOOL_LITERAL                  # boolLiteralExpr
     | array_literal_4d  # arrayLiteralExpr
     | array_literal_3d  # arrayLiteralExpr
     | array_literal_2d  # arrayLiteralExpr
     | array_literal_1d  # arrayLiteralExpr
     // END :: literals //
     | rect_sel_of_lattice_in_dfs  # rectSelOfLatticeInDFsExpr
     | rect_sel_of_array_elems     # rectSelOfArrayElemsExpr
     | identifier  # identifierExpr
     ;
