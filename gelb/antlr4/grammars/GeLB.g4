grammar GeLB;
import CommonLexerRules;

gelb_program :
        gelb_version_stmt
        // configuration_block
        // lattice_properties_block
        // lattices_block
        EOF ;

gelb_version_stmt : GELB_VERSION OP_ASSIGN NON_NEGATIVE_INT SEMICOLON ;

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
