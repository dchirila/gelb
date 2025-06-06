===========================
GeLB Developer Manual
===========================

A comprehensive guide for GeLB compiler developers and contributors.

**Note:** For general GeLB usage, installation, and language concepts, see the main README.rst

Overview
========

This manual covers the internal architecture and development processes of the GeLB compiler.
It is intended for developers who want to:

* Understand how the GeLB compiler works internally
* Contribute new features or bug fixes
* Extend the language with new constructs
* Add support for new target platforms
* Debug compilation issues

The manual is organized to take you from initial setup through advanced compiler topics.

.. include:: dev/01_getting_started.rst
.. include:: dev/02_architecture_overview.rst
.. include:: dev/03_compilation_pipeline.rst
.. include:: dev/04_grammar_and_parsing.rst
.. include:: dev/05_ast_system.rst
.. include:: dev/06_visitor_pattern.rst
.. include:: dev/07_frontend_pipeline.rst
.. include:: dev/08_symbol_resolution.rst
.. include:: dev/09_type_system.rst
.. include:: dev/10_midware_stage.rst
.. include:: dev/11_backend_codegen.rst
.. include:: dev/12_testing_framework.rst
.. include:: dev/13_debugging_tools.rst
.. include:: dev/14_extending_compiler.rst
.. include:: dev/appendix_design_decisions.rst