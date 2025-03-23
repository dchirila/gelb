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
      .\venv\Scripts\activate

      # On Unix/MacOS:
      source venv/bin/activate

* Install GeLB locally:

  .. code-block:: bash

      # Basic installation (core dependencies only)
      pip install -e .

      # Full installation with development tools
      pip install -e .[dev]

  After installation, the ``gelbc`` command-line tool will be available in your environment.
  
  The ``-e`` flag installs the package in "editable" mode, meaning:
  
  * Changes to Python code are immediately reflected without reinstallation
  * However, you must reinstall (``pip install -e .``) if you modify:
    
    - ``setup.py`` (dependencies, entry points)
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

* Update requirements.txt:

  .. code-block:: bash

      pip freeze > requirements.txt

* Render RST files to HTML:

  .. code-block:: bash

      rst2html FILE.rst FILE.html


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
