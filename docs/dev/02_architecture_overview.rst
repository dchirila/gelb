========================
Architecture Overview
========================

This document describes the high-level architecture of the GeLB compiler implementation.

Bird's Eye View
===============

The GeLB project provides:

1. **Specification of a Domain-Specific Language (DSL)** for Lattice Boltzmann simulations
2. **Support tools for the DSL** (reference compiler, debugging tools, etc.)

Main Goal
---------

**The main goal is to allow users to write high-level code describing the numerics of their simulations, and automatically translate that high-level code into high-performance code** (e.g., for taking advantage of GPUs or specialized hardware).

The specification focuses on high-level abstractions that make researchers and practitioners interested in Lattice Boltzmann methods more productive.

Language Specification
-----------------------

The formal definition of the GeLB language is found in the ANTLR4 grammar file: ``gelb/antlr_part/grammars/GeLB.g4``

Support Tools
-------------

The reference compiler is implemented as the ``gelb`` Python package, providing:

* **Reference compiler** for translating GeLB programs to target languages
* **Debugging and visualization tools** for development
* **Validation and error checking** at compile-time

Code Organization
=================

The GeLB compiler is organized into several key modules:

**Core Compilation Pipeline:**

* ``gelb/antlr_part/`` - ANTLR4 grammar and generated parser code
* ``gelb/frontend/`` - Stage 1: Parsing, AST building, type checking
* ``gelb/midware/`` - Stage 2: AST transformations and optimizations  
* ``gelb/backends/`` - Stage 3: Code generation for target platforms

**Supporting Infrastructure:**

* ``gelb/gelb_ast/`` - AST node definitions and utilities
* ``gelb/utils/`` - Shared utilities (error handling, visualization, etc.)
* ``gelb/tests/`` - Comprehensive test suite

**Entry Points:**

* ``gelb/gelbc.py`` - Main compiler driver
* ``scripts/`` - Development and maintenance scripts

Module Dependencies
-------------------

The compilation pipeline follows a clear dependency flow:

1. **ANTLR4 Generated Code** → **Frontend**
2. **Frontend** → **Midware** 
3. **Midware** → **Backend**
4. **AST Definitions** ← Used by all stages
5. **Utilities** ← Used by all stages

Three-Stage Compilation Pipeline
================================

Stage 1: Frontend
-----------------

**Input:** GeLB source code (text)  
**Output:** Fully analyzed and validated AST

**Responsibilities:**
* Lexical analysis and parsing (ANTLR4)
* Parse tree → AST conversion
* Symbol table construction  
* Constant resolution
* Range resolution (``:``) → concrete bounds)
* Type inference and promotion
* Type validation
* Semantic validation

**Key Files:**
* ``gelb/frontend/stage1_frontend.py`` - Main frontend orchestration
* ``gelb/frontend/ASTBuilderVisitor.py`` - Parse tree → AST conversion
* ``gelb/frontend/TypeInferenceVisitor.py`` - Type attribution
* ``gelb/frontend/SymbolsTablesBuilderVisitor.py`` - Symbol resolution

Stage 2: Midware  
----------------

**Input:** Validated AST from frontend  
**Output:** Optimized and transformed AST ready for code generation

**Responsibilities:**
* AST transformations and normalizations
* Optimization passes (future)
* Backend preparation
* Platform-specific lowering (future)

**Current State:** Minimal pass-through design for MVP
**Key Files:**
* ``gelb/midware/stage2_midware.py`` - Main midware processing

Stage 3: Backend
-----------------

**Input:** Transformed AST from midware  
**Output:** Target language code (Fortran, C++, etc.)

**Responsibilities:**
* Code generation for specific target languages
* Platform-specific optimizations
* Runtime library integration
* Build system generation

**Current Implementation:**
* ``gelb/backends/stage3_backend_cpu_serial_fortran.py`` - Fortran backend

Design Principles
=================

**Separation of Concerns**
Each stage has clearly defined responsibilities and interfaces.

**Extensibility**  
New language features can be added by extending the appropriate stage(s).

**Maintainability**
Clear module boundaries and comprehensive testing enable confident refactoring.

**Performance**
The architecture enables aggressive optimizations while maintaining correctness.

**Portability**
Clean abstractions allow targeting multiple platforms and languages.

Error Handling Philosophy
=========================

**Early Detection**
Catch errors as early as possible in the compilation pipeline.

**Clear Messages**
Provide actionable error messages with source location information.

**Graceful Degradation**
Continue compilation where possible to report multiple errors.

**Debugging Support**
Provide tools and visualizations to help diagnose compilation issues.

Cross-Cutting Concerns
======================

**Code Range Tracking**
All AST nodes maintain source location information for error reporting.

**Symbol Management**
Hierarchical symbol tables support proper scoping and name resolution.

**Type System**
Comprehensive type inference, promotion, and validation throughout the pipeline.

**Testing Infrastructure**  
Extensive unit and integration tests cover all major compiler components.

**Debugging Tools**
AST visualization and inspection tools aid in development and troubleshooting.