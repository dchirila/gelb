grammar GeLB;
import CommonLexerRules;

gelb_program: //
	// gelb_version_stmt //
	simulation_metadata_block
	// lattices_block //
	// initializer_block //
	// dynamic_block
	// gauge_block
	// node_classes_block
	// geometry_block
	EOF;

// gelb_version_stmt: GELB_VERSION OP_ASSIGN NON_NEGATIVE_INTEGER SEMICOLON ;

simulation_metadata_block: SIMULATION_METADATA CURLY_OPEN
	set_short_name_stmt
	set_description_stmt
CURLY_CLOSE;

set_short_name_stmt: SHORT_NAME OP_ASSIGN STRING SEMICOLON;
set_description_stmt: DESCRIPTION OP_ASSIGN STRING SEMICOLON;

// lattices_block: //
// 	LATTICES CURLY_OPEN //
// 	lattice_instantiation //
// 	CURLY_CLOSE;

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

// gelb_program :
        // gelb_version_stmt
        // configuration_block
        // lattice_properties_block
        // lattices_block
        // EOF ;

// gelb_version_stmt : GELB_VERSION OP_ASSIGN NON_NEGATIVE_INT SEMICOLON ;

// configuration_block : CONFIGURATION LCURLY
//         simulation_metadata_sub_block
//         global_constants_sub_block
//         RCURLY ;

// simulation_metadata_sub_block : SIMULATION_METADATA LCURLY
//         short_name_stmt
//         description_stmt
//         RCURLY ;

// short_name_stmt : SHORT_NAME OP_ASSIGN STRING SEMICOLON ;

// description_stmt : DESCRIPTION OP_ASSIGN STRING SEMICOLON ;

// global_constants_sub_block : CONSTANTS LCURLY
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

// lattice_properties_block : LATTICE_PROPERTIES ID LCURLY
//         const_decl_stmt*
//         RCURLY ;

// lattices_block : LCURLY RCURLY ;