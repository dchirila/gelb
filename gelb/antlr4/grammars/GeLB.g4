grammar GeLB;
import CommonLexerRules;

gelb_program: //
	set_simulation_name_stmt
	set_simulation_description_stmt
	// global_constants_block
	lattices_block
	// initializer_block //
	// dynamic_block
	// gauge_block
	// function_block
	// node_classes_block
	// geometry_block
	EOF;

set_simulation_name_stmt: SIMULATION_NAME OP_ASSIGN STRING SEMICOLON;
set_simulation_description_stmt: SIMULATION_DESCRIPTION OP_ASSIGN STRING SEMICOLON;

lattice_properties_block: LATTICE_PROPERTIES ID CURLY_OPEN
	TODO // const_decl_stmt*
CURLY_CLOSE;

lattices_block: LATTICES CURLY_OPEN
	TODO // lattice_instantiation_stmt+ // a program needs at least one lattice!
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


// **** TMP **** //

// global_constants_block: GLOBAL_CONSTANTS LCURLY
//         const_decl_stmt*
//         RCURLY ;

// const_decl_stmt : CONST data_type
//         sub_decl_with_val (COMMA sub_decl_with_val)*
//         SEMICOLON ;

// data_type : scalar_data_type
//           | array_data_type ;

// scalar_data_type : scalar_bool_data_type
//                  | scalar_int_data_type
//                  | scalar_real_data_type ;

// scalar_bool_data_type : BOOL ;

// scalar_int_data_type : INT64
//                      | INT32
//                      | INT16
//                      | INT8
//                      | INT ;

// scalar_real_data_type : REAL64
//                       | REAL32
//                       | REAL16
//                       | REAL ;

// array_data_type : ARRAY OP_LT scalar_data_type COMMA list_literal OP_GT ;

// // TODO generalize this
// list_literal : LCURLY
//         list_literal_atom
//         (COMMA list_literal_atom)*
//         RCURLY ;

// list_literal_atom : list_literal | expr ;

// expr : NON_NEGATIVE_INT ;

// sub_decl_with_val : ID OP_ASSIGN NON_NEGATIVE_INT ;