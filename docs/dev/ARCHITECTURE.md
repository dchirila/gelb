# Architecture

This document describes the high-level architecture of the reference GeLB
implementation. If you plan to contribute to GeLB and want to familiarize
yourself with the code, this is where you should begin!

## Bird's Eye View

On the highest level, the GeLB project provides:

1. the specification of a domain-specific language (DSL), and
2. support tools for the DSL (reference compiler, editor/IDE plugins, etc.)

### Specification of the DSL and main goal

The specification of the DSL was probably the most time-consuming part of the
project, because it required a lot of thinking and analyzing of patterns
encountered in typical LB implementations. The aim was to define a set of
high-level abstractions, which would make researchers (and tinkerers)
interested in Lattice Boltzmann (LB) methods more productive. **The main goal
is to allow users to write high-level code (describing *the numerics* of the
simulations they want), and to automatically translate that high-level code
into *high-performance code* (e.g. for taking advantage of GPUs or FPGAs).**

The specification of the GeLB language is explained in the [GeLB User
Guide](TODO-insert-link-to-user-guide), especially in the [Main
abstractions](TODO-insert-link-to-main-abstractions-at-user-guide) section.

Those interested in a formal definition of the GeLB language may look at the
[ANTLR4 Grammar File](TODO-insert-link-to-GeLB.g4).

### Support tools for the DSL

Of course, a DSL specification is of little use on its own, if there are no
tools to actually *use* the language. At the minimum, we want to have at
least:

* a reference compiler, and
* some plugins for a few popular code-editors & IDEs.

The reference compiler was written as the
[`gelb`](TODO-insert-link-to-gelb-at-pypi) Python 3 package (which you can
install with the command `pip install gelb`).

When editing `.gelb` files, it is useful to have some support, in the form of:

* syntax highlighting (of keywords, strings, comments, etc.),
* auto-completion, and
* (ideally) live validation of the code.

We take these things for granted when we use popular languages, but they need
to be defined (almost) from scratch when we introduce a new language.

## Code Map

TODO

## Cross-Cutting Concerns

TODO

## TODO: Organize

- I could have used other implementation languages (e.g. C++, Kotlin, or
JavaScript), but they all make it harder to interact with SymPy (which was one
one of the core libraries that I decided to use early-on).