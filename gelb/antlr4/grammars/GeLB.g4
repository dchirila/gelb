grammar GeLB;
import CommonLexerRules;

gelb_program: //
	gelb_version_stmt //
	// lattices_block //
	// initializer_block //
	// dynamic_block
	// gauge_block
	// node_classes_block
	// geometry_block
	EOF;

gelb_version_stmt: GELB_VERSION OP_ASSIGN NON_NEGATIVE_INTEGER SEMICOLON ;

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