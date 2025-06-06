========================
Grammar and Parsing
========================

This section covers the ANTLR4 grammar system used in GeLB and how to work with it effectively.

ANTLR4 Labels
=============

ANTLR4 labels are used throughout the GeLB grammar to make the generated parser code more readable and the visitor implementation cleaner.

What are ANTLR4 Labels?
------------------------

ANTLR4 labels are annotations you can add to grammar rules to give names to rule elements. They make it easier to access specific parts of a parsed rule in your visitor or listener code.

Types of Labels
---------------

1. **Simple Labels (=)**
   
   Used to label a single element in a rule::

       variable_assignment_stmt :
           lhs=identifier OP_ASSIGN rhs=expr SEMICOLON ;

   In the visitor, you can access these as ``ctx.lhs`` and ``ctx.rhs`` instead of ``ctx.identifier()`` and ``ctx.expr()``.

2. **List Labels (+=)**
   
   Used when an element can appear multiple times::

       rect_sel_of_array_elems :
           array_name=identifier BRACKET_OPEN
           ranges+=coords_range (COMMA ranges+=coords_range)*
           BRACKET_CLOSE ;

   The ``+=`` operator collects all matching elements into a list. In the visitor, ``ctx.ranges`` will be a list containing all ``coords_range`` elements.

3. **Alternative Labels (#)**
   
   Used to label alternatives in a rule::

       coords_range : low=expr                  # singleElementRange
                    | low=expr COLON high=expr  # lowhighBoundRange
                    | low=expr COLON            # lowBoundRange
                    |          COLON high=expr  # highBoundRange
                    |          COLON            # allElementsRange
                    ;

   ANTLR generates separate visitor methods for each alternative: ``visitSingleElementRange()``, ``visitLowhighBoundRange()``, etc.

Benefits of Using Labels
------------------------

1. **More Readable Code**: Instead of ``ctx.expr(0)`` and ``ctx.expr(1)``, you can use ``ctx.left`` and ``ctx.right``.

2. **Self-Documenting Grammar**: Labels make the grammar easier to understand.

3. **Type Safety**: With labels, you know exactly what type to expect.

4. **Simplified Visitor Code**: Compare these two approaches:

   Without labels::

       def visitVariable_assignment_stmt(self, ctx):
           lhs = self.visit(ctx.identifier())
           rhs = self.visit(ctx.expr())

   With labels::

       def visitVariable_assignment_stmt(self, ctx):
           lhs = self.visit(ctx.lhs)
           rhs = self.visit(ctx.rhs)

Examples from GeLB Grammar
--------------------------

1. **Assignment Statement**::

       lattice_out_selection_assignment_stmt :
           lhs=rect_sel_of_lattice_out_dfs
           OP_ASSIGN
           rhs=expr
           SEMICOLON ;

2. **Array Selection with List Labels**::

       rect_sel_of_lattice_in_dfs:
           lattice_name=identifier DOT IN
           BRACKET_OPEN
           spatial_ranges+=coords_range (COMMA spatial_ranges+=coords_range)*
           dfs_range=lattice_dfs_range
           BRACKET_CLOSE ;

3. **Expression Alternatives**::

       expr : PAREN_OPEN expr PAREN_CLOSE                # parensExpr
            | left=expr op=(OP_MUL | OP_DIV) right=expr  # infixExpr
            | left=expr OP_AND right=expr                 # logicalAndExpr
            | value=NON_NEGATIVE_INT_LITERAL              # nonNegIntLiteralExpr
            ;

Important Gotchas
-----------------

When using ANTLR4 labels in Python projects, be aware of these potential issues:

1. **Python Keyword Conflicts**: If you use a label name that conflicts with a Python keyword, ANTLR4 automatically adds an underscore suffix to the generated Python code.

   Example::

       // In grammar:
       constant_definition_stmt : CONST type=data_type assignment=variable_assignment_stmt ;
       
       // In Python visitor:
       data_type = self.visit(ctx.type_)  # Note: type_ not type

   Common Python keywords to avoid: ``type``, ``class``, ``def``, ``if``, ``for``, ``while``, ``import``, etc.

2. **Grammar Rule Name Conflicts**: You cannot use a label name that matches an existing grammar rule name.

   Example::

       // This will cause an error:
       constant_definition_stmt : CONST data_type=data_type assignment=variable_assignment_stmt ;
       //                              ^^^^^^^^^ label name conflicts with rule name
       
       // Correct approach:
       constant_definition_stmt : CONST type=data_type assignment=variable_assignment_stmt ;

Best Practices
--------------

1. Use descriptive label names that indicate the role of the element
2. Be consistent with naming across similar rules
3. Use ``+=`` for elements that can repeat
4. Use ``#`` labels for alternatives that need different processing logic
5. Don't overuse labels - only add them where they improve clarity
6. Avoid Python keywords and existing grammar rule names when choosing label names
7. Document any keyword conflicts with comments in both grammar and visitor code

Grammar Structure
=================

The GeLB grammar is organized into several files in ``gelb/antlr_part/grammars/``:

**Main Grammar File**
* ``GeLB.g4`` - Complete GeLB language grammar

**Supporting Files**  
* ``CommonLexerRules.g4`` - Shared lexer rules and tokens

Grammar Organization
--------------------

The grammar follows a hierarchical structure:

1. **Program Structure** - Top-level program organization
2. **Block Definitions** - Different block types (lattices, initializer, etc.)
3. **Statements** - Assignment statements, declarations
4. **Expressions** - Arithmetic, logical, comparison expressions
5. **Literals and Identifiers** - Terminal symbols
6. **Lexer Rules** - Tokens and keywords

Parse Tree to AST Conversion
============================

The ``ASTBuilderVisitor`` class converts ANTLR4 parse trees into GeLB AST nodes:

**Key Principles:**
* One-to-one mapping from parse tree nodes to AST nodes where possible
* Eliminate parsing artifacts (parentheses, separators)
* Add semantic information (types, resolved symbols)
* Preserve source location information for error reporting

**Example Conversion:**

Parse tree for ``x = 1 + 2;``::

    variable_assignment_stmt
    ├── lhs: identifier['x']
    ├── OP_ASSIGN['=']  
    ├── rhs: expr
    │   ├── left: expr
    │   │   └── value: NON_NEGATIVE_INT_LITERAL['1']
    │   ├── op: OP_ADD['+']
    │   └── right: expr
    │       └── value: NON_NEGATIVE_INT_LITERAL['2']
    └── SEMICOLON[';']

Becomes AST::

    VariableAssignmentStmt_N
    ├── lhs: Identifier_N('x')
    └── rhs: Add_N
        ├── left: IntLiteral_N(1)
        └── right: IntLiteral_N(2)

Adding New Language Constructs
===============================

To add a new language feature:

1. **Update Grammar** - Add new rules to ``GeLB.g4``
2. **Regenerate Parser** - Run ``./scripts/regenerate_antlr.sh``
3. **Add AST Nodes** - Create new node types in ``gelb_ast/ASTNodes.py``
4. **Update ASTBuilderVisitor** - Add conversion methods
5. **Update Other Visitors** - Add handling in all relevant visitors
6. **Add Tests** - Create comprehensive test coverage

Grammar Maintenance Guidelines
==============================

**Version Control**
* Always commit grammar changes with regenerated files
* Include clear commit messages explaining grammar changes
* Test thoroughly before committing

**Documentation**
* Update grammar documentation when adding features
* Include examples of new syntax in comments
* Document any design decisions or trade-offs

**Testing**
* Add parsing tests for new constructs
* Test error cases and edge conditions
* Verify AST building works correctly

**Backward Compatibility**
* Consider impact on existing programs
* Deprecate features gracefully when possible
* Document breaking changes clearly