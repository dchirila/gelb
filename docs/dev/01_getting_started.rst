============================
Getting Started with Development
============================

This section covers setting up your development environment for GeLB compiler development.

Development Environment Setup
=============================

Prerequisites
-------------

* Python 3.12 or higher
* Git for version control
* Operating system: Windows, Linux, or macOS
* Disk space: At least 500MB for the virtual environment and dependencies
* Internet connection for the initial downloading of dependencies
* Text editor or IDE with RST support (recommended)
* Basic knowledge of command-line interfaces

No Java installation is required as ANTLR4 tools are managed through Python packages.

Environment Setup
------------------

Set up the development environment:

.. code-block:: bash

    # On Windows:
    .\scripts\gelb_bootstrap.ps1

    # On Unix/MacOS:
    ./scripts/gelb_bootstrap.sh

Activate the virtual environment:

.. code-block:: bash

    # On Windows:
    .\.venv\Scripts\activate

    # On Unix/MacOS:
    source .venv/bin/activate

Install GeLB locally:

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

Development Workflow
====================

Running Tests
-------------

.. code-block:: bash

    # Run all tests
    pytest

    # Run specific test file
    uv run pytest gelb/tests/type_inference/test_type_inference_paint_nodes.py

    # Run specific test class
    uv run pytest gelb/tests/type_inference/test_type_inference_paint_nodes.py::TestPaintNodesTypeInference

    # Run specific test method
    uv run pytest gelb/tests/type_inference/test_type_inference_paint_nodes.py::TestPaintNodesTypeInference::test_paint_nodes_with_constant_ranges

    # Alternative: Use -k to match test name pattern
    uv run pytest gelb/tests/type_inference/test_type_inference_paint_nodes.py -k "test_paint_nodes_with_constant_ranges"

    # Common pytest flags:
    # -x  : stop on first failure
    # -v  : verbose output
    # -s  : show print statements
    # -xvs: combine all three flags (recommended for debugging)

ANTLR4 Grammar Regeneration
----------------------------

.. code-block:: bash

    # On Windows:
    .\scripts\regenerate_antlr.ps1

    # On Unix/MacOS:
    ./scripts/regenerate_antlr.sh

Note: These scripts require the virtual environment to be set up first.
They will regenerate all ANTLR4-generated files based on the GeLB grammar.
The files are also automatically regenerated when running tests.

Cleaning Generated Files
------------------------

.. code-block:: bash

    # On Windows:
    .\scripts\cleanup_repo.ps1

    # On Unix/MacOS:
    ./scripts/cleanup_repo.sh

Dependency Management
---------------------

.. code-block:: bash

    # Dependencies are managed in pyproject.toml
    # To add a new dependency:
    uv add package-name
    
    # To add a development dependency:
    uv add --dev package-name

Documentation Rendering
------------------------

.. code-block:: bash

    rst2html FILE.rst FILE.html

Important Notes for Developers
===============================

**uv Virtual Environment Usage:**

The project uses uv for Python package management. When running Python commands:

.. code-block:: bash

    # ✅ CORRECT - Use uv run to execute commands in the virtual environment
    uv run python gelb/gelbc.py example.gelb
    uv run pytest gelb/tests/unit/test_something.py
    uv run python -m some_module

    # ❌ WRONG - Don't run Python directly without uv
    python gelb/gelbc.py example.gelb  # May use wrong Python version or missing dependencies

**Key uv commands:**
- ``uv sync --all-extras`` - Install all dependencies including dev tools
- ``uv pip install -e .`` - Install GeLB in editable mode
- ``uv add package-name`` - Add a new dependency
- ``uv add --dev package-name`` - Add a development dependency
- ``uv run command`` - Run any command in the virtual environment context