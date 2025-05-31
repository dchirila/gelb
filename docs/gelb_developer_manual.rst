=====================
GeLB developer manual
=====================

Development Environment
=======================

* Prerequisites:

  - Python 3.12 or higher
  - Git for version control
  - Operating system: Windows, Linux, or macOS
  - Disk space: At least 500MB for the virtual environment and dependencies
  - Internet connection for the initial downloading of dependencies
  - Text editor or IDE with RST support (recommended)
  - Basic knowledge of command-line interfaces
  
  No Java installation is required as ANTLR4 tools are managed through Python packages.

* Set up the development environment:

  .. code-block:: bash

      # On Windows:
      .\scripts\gelb_bootstrap.ps1

      # On Unix/MacOS:
      ./scripts/gelb_bootstrap.sh

* Activate the virtual environment:

  .. code-block:: bash

      # On Windows:
      .\.venv\Scripts\activate

      # On Unix/MacOS:
      source .venv/bin/activate

* Install GeLB locally:

  .. code-block:: bash

      # Basic installation (core dependencies only)
      uv pip install -e .

      # Full installation with development tools
      uv sync --all-extras

  After installation, the ``gelbc`` command-line tool will be available in your environment.
  
  The ``-e`` flag installs the package in "editable" mode, meaning:
  
  * Changes to Python code are immediately reflected without reinstallation
  * However, you must reinstall (``uv pip install -e .``) if you modify:
    
    - ``pyproject.toml`` (dependencies, entry points)
    - Package metadata
    - Non-Python files

* Run the tests:

  .. code-block:: bash

      pytest

* Clean up generated files:

  .. code-block:: bash

      # On Windows:
      .\scripts\cleanup_repo.ps1

      # On Unix/MacOS:
      ./scripts/cleanup_repo.sh

* Regenerate ANTLR4 files:

  .. code-block:: bash

      # On Windows:
      .\scripts\regenerate_antlr.ps1

      # On Unix/MacOS:
      ./scripts/regenerate_antlr.sh

  Note: These scripts require the virtual environment to be set up first.
  They will regenerate all ANTLR4-generated files based on the GeLB grammar.
  The files are also automatically regenerated when running tests.

* Update dependencies:

  .. code-block:: bash

      # Dependencies are managed in pyproject.toml
      # To add a new dependency:
      uv add package-name
      
      # To add a development dependency:
      uv add --dev package-name

* Render RST files to HTML:

  .. code-block:: bash

      rst2html FILE.rst FILE.html


ANTLR4 Labels
=============

This section explains ANTLR4 labels, which are used throughout the GeLB grammar to make the generated parser code more readable and the visitor implementation cleaner.

What are ANTLR4 Labels?
-----------------------

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

Abstract Syntax Tree (AST)
==========================

Definition: TODO

Despite their name, there is nothing abstract about the trees themselves
(although they can have size-induced complexity, for non-trivial programs).
Instead, the word "abstract" refers to the fact that some of the syntax is
"abstracted-away" (e.g. the AST for a language from the C family would not
include separator keywords, parentheses or the semicolon at the end of each
instruction). This is in contrast with *parse trees* (also known as *concrete
syntax trees*), which contain all of these low-level syntax elements.

"Each node of the tree denotes a construct occurring in the source code."

Benefits of using ASTs (& motivation for using them):

- They make program analysis and program transformation systems easier to
  implement (compared to working directly on the source-code, or on the parse
  trees).

- AST nodes can be enhanced with additional information, which is deduced as the
  AST passes through the different `MidWare` stages within the GeLB compiler
  (something which would be impossible if working directly with the source-code,
  and cumbersome if working with the syntax trees).


Types of Nodes in the GeLB AST
==============================

NOTEs:

- All AST Nodes inherit from the **Node** class, which has:

  - Attributes:

    - start
    - end

    NOTE: {start, end} are positions in the original input-stream, which
    allow us to provide more informative error-messages

  - Methods:

    - TODO

- **Program**

  - simulation_description -> **StringLit**
  - lattices -> **List** (**Lattice** )
  - node_classes -> **List** (**NodeClass**)
  - initializers -> **List** (**Initializer**)
  - dynamics -> **List** (**Dynamic**)
  - gauges -> **List** (**Gauge**)
  - functions -> **List** (**Function**)
  - geometry -> **StructuredGeometry** | **GeneralGeometry**

- **Lattice**
  TODO

- **NodeClass**
  TODO

- **Initializer**
  TODO

- **Dynamic**
  TODO

- **Gauge**
  TODO

- **Function**
  TODO

- **StructuredGeometry**
  TODO

- **Scalar** types

  - **BoolLit**
    TODO

  - **NumIntLit**
    TODO

  - **NumRealLit**
    TODO

  - **StringLit**
    TODO


Range Syntax and Resolution
===========================

GeLB supports flexible range syntax for selecting array elements, lattice sites, and distribution functions. Understanding how ranges work is crucial for compiler development.

Range Syntax
------------

GeLB supports four range patterns:

* ``:`` - All elements (e.g., ``nodes[:] = BULK``)
* ``low:`` - From ``low`` to end (e.g., ``nodes[5:] = BULK``)
* ``:high`` - From start to ``high`` (e.g., ``nodes[:10] = BULK``)
* ``low:high`` - Specific range (e.g., ``nodes[5:10] = BULK``)

Range patterns appear in multiple contexts:

* Geometry: ``nodes[:, :] = BULK`` (2D all nodes)
* Lattice selections: ``f.out[x, y | :]`` (all distribution functions)
* Array access: ``f.E[0, :]`` (all elements in second dimension)

AST Traversal Challenge
-----------------------

The range syntax creates ``Range_N`` AST nodes where missing bounds are represented as ``None``:

* ``:`` creates ``Range_N(low=None, high=None)``
* ``5:`` creates ``Range_N(low=5, high=None)``
* ``:10`` creates ``Range_N(low=None, high=10)``

This caused AST traversal methods to crash when encountering ``None`` values during recursive descent.

Resolution Strategy
-------------------

The issue was resolved with a two-part approach:

**Part 1: Defensive AST Methods**
  Added ``None`` checks to base ``Node_N`` class methods (see ``gelb/gelb_ast/ASTNodes.py``)::

    if child is None:  # Handle None fields
        continue

**Part 2: Range Resolution**
  Implemented ``RangeResolverVisitor`` (see ``gelb/frontend/RangeResolverVisitor.py``) that replaces ``None`` bounds with concrete expressions:

  * ``None`` lower bound → ``0``
  * ``None`` upper bound → ``Nx-1``, ``Ny-1``, or ``Nz-1`` (spatial dimensions)
  * ``None`` upper bound → ``q-1`` (distribution function ranges)

Integration
-----------

Range resolution runs in the compilation pipeline after symbol table construction::

    ast = build_symbols_tables(ast)
    ast = resolve_all_constants(ast)
    ast = resolve_ranges(ast)  # ← Range resolution here
    validate_node_classes(ast)

See ``gelb/gelbc.py`` for the complete pipeline and ``gelb/frontend/stage1_frontend.py`` for the ``resolve_ranges()`` function.

Testing
-------

Comprehensive tests cover various range scenarios in ``gelb/tests/more_frontend_validation/test_range_resolver_visitor.py``. All GeLB examples now compile successfully with proper range resolution.
