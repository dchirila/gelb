grammar GeLB;
import CommonLexerRules;

/*
 Root grammar rule, for an entire GeLB program.

 NOTE: We want to allow users to specify the block in any order they like.
       To achieve this, we use the pattern:
       gelb_program : ( block_type1 | block_type 2 | ... )* ;

       Later, in ASTBuilderVisitor.visitGelb_program, we enforce some rules,
       e.g. that the number of occurrences of each block-type is valid.
       
 NOTE: This grammar uses ANTLR4 labels (= and +=) to make the generated parser
       more readable and the visitor code cleaner.
       
       IMPORTANT ANTLR4 Label Gotchas:
       1. Labels that conflict with Python keywords get an underscore suffix
          (e.g., 'type' becomes 'ctx.type_' in Python visitor code)
       2. Labels cannot have the same name as existing grammar rules
          (e.g., cannot use 'data_type=data_type')
 */
gelb_program : // Valid # of occurrences (as interval)
	( set_simulation_description_stmt  // [1, 1]
	| global_constants_block           // [0, 1]
	| lattices_block                   // [1. 1]
    | initializer_block                // [1, oo)
	| dynamic_block                    // [1, oo)
	| gauge_block                      // [1, oo)
	| function_block                   // [0, oo)
	| node_classes_block               // [1, 1]
	| geometry_block                   // [1, 1]
	)*
	EOF ;

set_simulation_description_stmt : SIMULATION_DESCRIPTION PAREN_OPEN
    STRING_LITERAL
PAREN_CLOSE SEMICOLON ;

// When this optional block is present...
global_constants_block: GLOBAL_CONSTANTS CURLY_OPEN
    // it should contain at least one constant definition
    constant_definition_stmt+
CURLY_CLOSE ;

lattices_block : LATTICES CURLY_OPEN
    // NOTE: a program needs at least one lattice!
    // DESIGN DECISION: Constants are not allowed in the lattices block.
    // All constants must be defined either:
    // - In the global_constants_block (for global constants)
    // - Inside initializer/dynamic/gauge blocks (for local constants)
    // This keeps the lattices block focused solely on lattice declarations.
	lattice_insta_stmt+
CURLY_CLOSE ;

lattice_insta_stmt :                   // Example:
    LATTICE name=identifier PAREN_OPEN   // lattice f(
 	d=expr                               //   d=2,
 	COMMA q=expr                         //   q=9,
 	COMMA df_type=scalar_data_type       //   df_type=int64,
 	COMMA grid_size=expr                 //   grid_size=32,
 	COMMA periodicity=expr               //   periodicity=false
 	PAREN_CLOSE SEMICOLON ;              // );

block_stmt : constant_definition_stmt
           | variable_declaration_stmt
           | variable_declaration_with_init_stmt
           // BEGIN :: assignment stmts //
           | lattice_out_selection_assignment_stmt
           | variable_assignment_stmt
           | array_selection_assignment_stmt
           | destructuring_assignment_stmt
           // END :: assignment stmts //
           ;

destructuring_assignment_stmt :
    CURLY_OPEN
    targets+=identifier (COMMA targets+=identifier)*
    CURLY_CLOSE
    OP_ASSIGN rhs=expr SEMICOLON ;

initializer_block :
    INITIALIZER identifier CURLY_OPEN
 	block_stmt+
 	CURLY_CLOSE ;

dynamic_block :
    DYNAMIC identifier CURLY_OPEN
 	block_stmt+
    CURLY_CLOSE ;

gauge_block :
    GAUGE name=identifier
    // The entire result clause is optional so semantic validation can
    // provide a useful diagnostic for a bare gauge.
    (ARROW PAREN_OPEN
        (results+=param_decl (COMMA results+=param_decl)*)?
        PAREN_CLOSE)?
    CURLY_OPEN
    block_stmt+  // core statements
    CURLY_CLOSE ;

function_block :
    FUNCTION name=identifier
    PAREN_OPEN
        (params+=param_decl (COMMA params+=param_decl)*)?
    PAREN_CLOSE
    ARROW
    PAREN_OPEN
        (results+=param_decl (COMMA results+=param_decl)*)?
    PAREN_CLOSE
    CURLY_OPEN
    block_stmt+
    CURLY_CLOSE ;

node_classes_block : NODE_CLASSES CURLY_OPEN  // node_classes {
    node_class_insta_stmt+  // node_class BULK(SetDFsToZero, IncrementDFs, CurrentState)
    CURLY_CLOSE ;                             // }

// node_class instantiation statement.
//
// A node class always names an initializer.  Whether it has a dynamic
// (collision/streaming step) or a gauge (output) is what makes the
// shape of this rule non-trivial.
//
// UNMASKED node classes (active cells with output):
//   * 3 args: init + dynamic + gauge       -- typical fluid cell
//   * 2 args: init + gauge  (no dynamic)   -- static cell with output
//
// MASKED node classes (cells skipped at runtime, NaN-filled in output):
//   * 2 args: init + dynamic + 'masked'    -- bounce-back wall, etc.
//   * 1 arg : init + 'masked'              -- static masked cell
//   * 0 args: 'masked'                     -- pure-solid marker
//
// IMPORTANT: masked node classes CANNOT have a gauge.  This is enforced
// at the grammar level (not by a separate validator) -- there is no
// 3-identifier alternative followed by MASKED.  The rationale is that
// masked cells are skipped during the gauge sweep and the corresponding
// output positions are NaN-filled, so a per-cell gauge would never run.
node_class_insta_stmt
    : NODE_CLASS identifier PAREN_OPEN            // unmasked: 2-3 args
      identifier COMMA identifier (COMMA identifier)?
      PAREN_CLOSE SEMICOLON
    | NODE_CLASS identifier PAREN_OPEN            // masked: 1-2 args
      identifier (COMMA identifier)?
      PAREN_CLOSE MASKED SEMICOLON
    | NODE_CLASS identifier PAREN_OPEN            // masked: 0 args
      PAREN_CLOSE MASKED SEMICOLON
    ;

geometry_block : GEOMETRY CURLY_OPEN
    geometry_stmt+
    CURLY_CLOSE ;

geometry_stmt : paint_nodes_stmt
             | conditional_paint_stmt
             | border_stmt ;

paint_nodes_stmt : NODES BRACKET_OPEN  // nodes[
    coords_range (COMMA coords_range)*
    BRACKET_CLOSE OP_ASSIGN           // ] =
    identifier SEMICOLON ;            // BULK ;

// Predicate paint: every cell for which the boolean expression holds is
// painted.  The expression sees the implicit coordinates (x; x, y; or
// x, y, z, by rank), constants and pure user functions, and is evaluated
// at compile time.  `where` keeps it distinct from a point paint
// `nodes[x0, y0] = C;`.
conditional_paint_stmt : NODES BRACKET_OPEN WHERE  // nodes[where
    predicate=expr                                //   InCircle(x, y, CX, CY, R)
    BRACKET_CLOSE OP_ASSIGN                       // ] =
    node_class=identifier SEMICOLON ;             // SOLID ;

border_stmt : BORDER PAREN_OPEN       // border(
    source=identifier                 //   SOLID
    PAREN_CLOSE OP_ASSIGN             // ) =
    target=identifier SEMICOLON ;     // WALL ;

lattice_out_selection_assignment_stmt :
    lhs=rect_sel_of_lattice_out_dfs
    OP_ASSIGN
    rhs=expr
    SEMICOLON ;

rect_sel_of_lattice_out_dfs:
    lattice_name=identifier DOT OUT
    BRACKET_OPEN
    spatial_ranges+=coords_range (COMMA spatial_ranges+=coords_range)*  // spatial ranges
    dfs_range=lattice_dfs_range
    BRACKET_CLOSE ;

rect_sel_of_lattice_in_dfs:
    lattice_name=identifier DOT IN
    BRACKET_OPEN
    spatial_ranges+=coords_range (COMMA spatial_ranges+=coords_range)*  // spatial ranges
    dfs_range=lattice_dfs_range
    BRACKET_CLOSE ;

rect_sel_of_array_elems :
    array_name=identifier BRACKET_OPEN
    ranges+=coords_range (COMMA ranges+=coords_range)*
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

// NOTE: Label 'type' becomes 'type_' in Python due to keyword conflict
constant_definition_stmt : CONST type=data_type assignment=variable_assignment_stmt ;

// NOTE: Label 'type' becomes 'type_' in Python due to keyword conflict
variable_declaration_stmt : type=data_type name=identifier SEMICOLON ;

// Function parameters and named results omit the statement terminator.
// NOTE: Label 'type' becomes 'type_' in Python due to keyword conflict.
param_decl : type=data_type name=identifier ;

variable_declaration_with_init_stmt : type=data_type assignment=variable_assignment_stmt ;

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
    element_type=scalar_data_type
    COMMA
    shape=array_shape
BRACKET_CLOSE ;

array_shape : array_literal_1d | expr ;

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
    elements+=array_literal_3d (COMMA elements+=array_literal_3d)+
CURLY_CLOSE ;

array_literal_3d : CURLY_OPEN
    elements+=array_literal_2d (COMMA elements+=array_literal_2d)+
CURLY_CLOSE ;

array_literal_2d : CURLY_OPEN
    elements+=array_literal_1d (COMMA elements+=array_literal_1d)+
CURLY_CLOSE ;

array_literal_1d : CURLY_OPEN
    elements+=expr (COMMA elements+=expr)+
CURLY_CLOSE ;

variable_assignment_stmt : lhs=identifier OP_ASSIGN
    rhs=expr
SEMICOLON ;

array_selection_assignment_stmt :
    lhs=rect_sel_of_array_elems
    OP_ASSIGN
    rhs=expr
    SEMICOLON ;

identifier : ID ;

/* OPERATOR PRECEDENCE (highest to lowest):
   1. Parentheses, literals, identifiers, array/lattice selections
   2. Power (^) - right associative
   3. Unary operators (+, -, !)
   4. Multiplication/Division (*, /)
   5. Addition/Subtraction (+, -)
   6. Comparison (<, >, <=, >=)
   7. Equality (==, !=)
   8. Logical AND (&&)
   9. Logical OR (||)
   
   This precedence matches standard conventions from C/C++, Python, Java, and FORTRAN.
   Examples: 2 + 3 * 4 = 14 (not 20)
            x > 5 && y < 10 means (x > 5) && (y < 10)
            a || b && c means a || (b && c)
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
     // NOTE: Negative numbers are handled via unary minus (see unaryExpr above)
     // Example: -3.14 becomes (UnaryMinusExpr (RealLiteral 3.14))
     | value=NON_NEGATIVE_REAL_LITERAL     # nonNegRealLiteralExpr
     | value=NON_NEGATIVE_INT_LITERAL      # nonNegIntLiteralExpr
     | value=BOOL_LITERAL                  # boolLiteralExpr
     | array_literal_4d  # arrayLiteralExpr
     | array_literal_3d  # arrayLiteralExpr
     | array_literal_2d  # arrayLiteralExpr
     | array_literal_1d  # arrayLiteralExpr
     // NOTE: STRING_LITERAL is intentionally excluded from expressions
     // to keep the language simpler. Strings are only used in specific
     // contexts like simulation description.
     // END :: literals //
     | rect_sel_of_lattice_in_dfs  # rectSelOfLatticeInDFsExpr
     | rect_sel_of_array_elems     # rectSelOfArrayElemsExpr
     | intrinsic_function_call     # intrinsicFunctionCallExpr
     | user_function_call          # userFunctionCallExpr
     | identifier  # identifierExpr
     ;

intrinsic_function_call : 
     intrinsic_function_name PAREN_OPEN 
     (arguments+=expr (COMMA arguments+=expr)*)? 
     PAREN_CLOSE ;

intrinsic_function_name : SUM | DOT_PROD | SIN | COS | SQRT | RANDOM | EXP | ABS | LOG | TAN | TANH | MIN | MAX | MOD | ATAN2 | UPSTREAM_DFS | BOUNCE_BACK_DFS | MATMUL | TRANSPOSE | INVERSE | DETERMINANT | INT | INT8 | INT16 | INT32 | INT64 | REAL | REAL16 | REAL32 | REAL64 ;

user_function_call :
    function_name=identifier PAREN_OPEN
    (arguments+=expr (COMMA arguments+=expr)*)?
    PAREN_CLOSE ;
