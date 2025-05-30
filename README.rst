=========================================================
GeLB: GEneric Lattice Boltzmann framework from the future
=========================================================

In essence, the GeLB framework provides:

* a domain-specific language (DSL), aiming to make LB researchers and tinkerers
  more productive, and
* support tools for the DSL.

In a nutshell, all GeLB programs (see also Fig. TODO) revolve around:

* `Lattice(s)`, which are essentially multi-dimensional arrays and

* `input / output` (IO) operations on `Lattice(s)`, for example:

  * *writing* some values to a `Lattice` -> `Initializer`

  * *updating* (which often implies *reading* **and** *writing*) a `Lattice` -> `Dynamic`

  * *reading* some values from a `Lattice` -> `Gauge`

Once you understand these four concepts (`Lattice`, `Initializer`, `Dynamic` and
`Gauge`), you understand most of what GeLB does -- the rest of this document
describes how GeLB supports these concepts.

TODO: Discuss concepts of {old,new}-Lattice (important for the syntax)!!!

As a programming language, GeLB is a hybrid -- while some aspects (definition of
operations to be performed on the lattice and specification of the simulation
geometry) are *imperative*, many other aspects are *declarative*. In other
words, it borrows ideas from both languages like `C(++)` or `Fortran`, as well
as from functional languages such as `Haskell`. However, that should not scare
you. We promise that there are no monads in GeLB. In fact, once you understand
some basic concepts and definition, GeLB is really easy to use. We hope that you
will enjoy it for learning about, playing, and even working with the LB method!

One of the notable aspects which are "hidden" from you as a GeLB user is the
strategy for mapping your simulation onto a (massively) parallel machine. The
basic premise of GeLB is that, by introducing a few restrictions in the
language, the mapping onto parallel hardware can be automated (although we
reserve the right to re-introduce *a few* of these details into future versions
of the language, as we add support for more-and-more hardware configurations).
To put this another way, users of GeLB should *NOT* assume any particular
ordering for the node-updates -- this allows GeLB to schedule updates in the
order it sees fit, to get good performance.

[OPPORTUNITY-TO-CONTRIBUTE] If you encounter a situation where you think GeLB
may not schedule node-updates optimally, we consider it a performance bug, and
encourage you to submit a bug report (or a pull request, in case you also found
the solution). *However, make sure that your solution does not depend on
optimizations which are "too narrow" (if unsure, submit the PR anyway :) ).*

Why have you created this?
==========================

We love numerical simulation in general (and LBM in particular). These ideas are
great to play with, and implementing the algorithms from scratch is actually a
great learning experience (leading to explorations of computer architecture and
how to get good performance, etc.). That said, when you want to *apply* the
method to a new physical problem (or compare variations of the LB algorithms),
many of the technical details start to get in the way -- there is a bug you need
to fix (which might be causing simulation stability issues), you need to
remember how to map the simulation on GPUs, you need to implement restart
support because your simulations keep crashing due to summer-induced datacenter
shutdowns, etc. Sometimes it can feel like these technical detours are actually
impacting the amount of science you can work on. We need better tools, to make
us more productive. In the case of LBM, the main author of GeLB somehow got
convinced that a better tool is possible. So, instead of just "plowing through"
the technicalities and getting on with the physics applications, he (somewhat
ironically) started going even deeper into the technical details, to implement
several prototypes which converged to the software described here. GeLB is the
LBM equivalent of a "supercar" that he would have liked to have from the
beginning of his LBM adventure. Now that the tool is done, if only he can still
remember what fluid dynamics problem he was working on to start with :).


About this document
===================

This document only provides:

- a (very) high-level overview of GeLB and 

- some instructions on installing it.

Please visit the GeLB.site_ for more in-depth documentation.

.. _GeLB.site: https://www.gelb.site/


Main features
=============

- Compiler for the GeLB language, which allows you to quickly write simulations based on the lattice Boltzmann method (LBM) or finite differences (FD)

- Expressive and intuitive syntax

- Built-in sanity checks (at *compile-time*) which prevent many types of bugs common in LBM implementations

- Automatic generation of GPU code (using OpenCL)


NON features
============

- `NULL` and `NA` support


Installation
============

Although we have tried to make GeLB as self-contained as possible, it *does*
depend on a fair number of libraries. GeLB provides convenient scripts to set up the
development environment and manage dependencies using uv (a fast Python package manager).

* Setup the development environment:

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

* Install GeLB in development mode:

  .. code-block:: bash

      uv pip install -e .

* (Optional) Clean up generated files:

  .. code-block:: bash

      # On Windows:
      .\scripts\cleanup_repo.ps1

      # On Unix/MacOS:
      ./scripts/cleanup_repo.sh

Limitations of the GeLB language
================================

Compared to most general-purpose languages (GPLs), the GeLB language imposes
several restrictions. While a few of these restrictions were chosen because they
would have delayed the release of the software, most of the restrictions are
actually intentional, s.t. the GeLB compiler has the best chance of producing
high-performance code for modern compute systems. We hope that users will find
that the existing abstractions allow them to express most of the LBM algorithms
they want to implement. However, some users will surely find features which they
will miss, in which case they are encouraged to contact the authors -- if many
users miss a particular feature, we will try to add it to a future version of
the language. Of course, users who are comfortable with compiler frameworks may
also implement such additional features themselves. However, to prevent
fragmentation of the language (and to ensure that GeLB programs are easily
interchangeable), we encourage you to submit a GitHub pull request (PR) if you
have implemented a feature which would be useful to the rest of the community.
Contributors are strongly encouraged to also read the *GeLB developer manual*.

Among the most notable restrictions, we mention:

- No `print` statement. The only way to generate output from a GeLB program is to
  use a `Gauge`. For a future version of the language, we are planning to add
  additional mechanisms to generate output (e.g. for monitoring simulations, or
  for making debugging easier).

- No support for classical program flow-control statements (`if-then-else`,
  `while` / `do` loops, `switch` statements, etc.). While this may be very
  surprising for some users, this restriction was very well-founded (such
  constructs are notoriously difficult to parallelize automatically, and they
  would also increase the complexity of the language significantly).

  However, many uses of such statements are supported by *intrinsic* functions
  of the language (e.g. `Sum`, `Product`, `DotProduct`, `VectorProduct`, `Min`,
  `Max`). If you discover that the language is missing a particular intrinsic
  function which you need for your work, feel free to contact the authors -- the
  library of intrinsic functions is still a work-in-progress.

  The `if-then-else` and `switch` statements will probably never be supported
  directly. However, there is one important case which *is* built into the
  language itself: whenever you need to have some special logic for some of the
  lattice nodes, you are encouraged to define a new `NodeCategory`, and assign
  those particular nodes to that category inside the `Geometry` block.

- All user-defined functions should be "pure", by which we mean that:

  - they should have a single return point, and

  - their return value should only depend on its input values, without side-effects.

    In other words, GeLB functions work similar to functions in mathematics (no
    local state, generation of output, asking for user input, etc.).

    This limitation also implies that a `Function` cannot *directly* access
    the lattice state. However, it *is* allowed to:

    - *write* to the lattice state the result of a `Function` call (within an `Initializer` or a `Dynamic`), as well as to

    - pass to a `Function` data which was *read* from the lattice state (within a `Dynamic` or a `Gauge`).

- No support for recursive functions (although such functions are also not
  forbidden, they may lead to sub-optimal performance or even undefined behavior
  on some platforms). Currently, we plan to explicitly forbid recursive
  functions in a future version of the language.

- No support for user-defined data-types. There is no plan to support this
  feature in the near future.

- No support for pointer data-types. These will (most probably) never be
  supported, because they would potentially break the model of abstractions at
  the core of the GeLB framework.

- No direct support for sparse domains, mesh-refinement, or non-Cartesian
  meshes. However, we are very interested in incorporating such advanced LBM
  algorithms into future versions of GeLB.


Names and reserved keywords
===========================

Valid GeLB names (identifiers) for user-defined entities (variables,
constants, lattices, initializers, dynamics, gauges, node-classes, etc.)
consist of a sequence of letters, digits and underscores (`_`).

.. warning:: The first character of a name *has* to be a letter.

The following words are reserved, and may not be used for naming user-defined
entities: `x`, `y`, `z` (which refer to the coordinates of the current node),
`lattice`, `lattices`, `int`, `true`, `false`, `initializer`, `dynamic`,
`gauge`, `in`, `out`, `node_classes`, `node_class`, `geometry`, `nodes`

TODO: Add keywords above, as they are added back to `CommonLexerRules.g4`.

GeLB names *are* case-sensitive, so `myvar` and `myVar` are treated as
different names (although it is, of course, *not* recommended to introduce
names which look so similar, due to readability concerns).

In general, try to choose names which describe the meaning of the entity, and
to be as consistent as possible with your naming scheme (e.g. adopt either
`camelCaseNames` or `underscore_separated_names`).


High-level concepts and revisions w.r.t. my PhD thesis
======================================================

If you have never heard about GeLB before, I recommend to read through the
GeLB paper TODO:insert-url-to-paper. After that, head to the GeLB.site_, for
more in-depth information and tutorials.

The GeLB framework was first mentioned in my PhD thesis
TODO:insert-url-to-thesis (Chapter 4). In case you read that discussion and
it piqued your interest, I am honored and humbled. In that write-up, I
briefly described the most important concepts of the language, which have
remained stable. That said, GeLB has evolved slightly from that initial
implementation (used for generating the results in my thesis). The most
important changes are listed below:

* The first obvious change concerns the naming of the text files containing
  user-written code to be processed by the GeLB compiler. In the thesis, I
  was referring to these as "GeLB Description (GD) programs/files". However,
  it turns out that there is no reason to burden the users with two acronyms
  ("GeLB" and "GD"). Also, the file extension `.gd` is already taken by other
  programming languages, which can create confusion. So, the decision has
  been made to replace all mentions of "GD" with "GeLB" within the
  documentation. Accordingly, the documentation now refers to "GeLB
  programs", which are stored in "GeLB files", which have the `.gelb` file
  extension. It is a trivial change which, however, hopefully saves you (and
  me) some time later.

* Programs no longer need to include a `gelb_version` statement.
  The idea behind this was to be able to specify which version of the language
  we are using.
  However, since **we do not plan to remove** any features from the language (at
  least, for the foreseeable future), coercing users to always type this is just
  pointless.
  So, removing this feature simplifies the compiler a little and, most
  importantly, it means that users have one less thing to worry about.
  A situation that *will* probably occur is that users who have installed an
  older version of `gelbc` attempt to use newer language features.
  For such scenarios, it is good to give users a warning, if they use an older
  version of the compiler.

  TODO: in the compiler, check whether a newer version of the compiler was
  published.

* The `simulation_name` statement is no longer required (because the name of
  the GeLB file is now used as the simulation name). This reduces the amount of
  boilerplate code users need to write, and also makes the language more consistent.

* In the `geometry` block, only rectangular node-selections are allowed, using
  the `nodes` statement (which is equivalent to the `node_range` statements in
  the thesis). The `node` statement is not needed (because it is just a special
  case of `nodes`), and the `read_geometry_from_file` statement needs more
  testing (will be added back soon).

* To avoid imposing one more constraint on the users, it is now possible to
  specify more than one `initializer` for each node-class. In the thesis, only
  one initializer was allowed for each node-class.

* The `size` and `periodicity` of the lattice(s) are now specified during
  lattice-instantiation (inside the `lattices` block). In the thesis, these
  were specified within the `geometry` block.

* The `gauge` out-specs and `function` {in,out}-specs are now given using
  parentheses (instead of square brackets), to bring the syntax closer to
  that of other programming languages.

* When specifying size & periodicity of the lattice(s), I think it is more
  natural to specify these during lattice-instantiation, so that we can have
  two lattices with different sizes & periodicity traits.

* The syntax for declaring *constant types* has changed slightly. Whereas in the
  thesis I was relying on the `_const` suffix, which was appended to the scalar
  data-types, in the final version of the language the `const` keyword is used,
  to make the syntax more natural to some programmers. Therefore, we use:

  * `const real pi = 3.14;` (instead of `real_const pi = 3.14;`) to declare and
    initialize a constant real value and

  * `const array[int, {2, 2}] I = {{1, 0}, {0, 1}};` to declare and initialize a
    constant array of integers.

* The syntax for declaring array types has changed from angle brackets to square
  brackets. In the thesis, array types were declared as `array<element_type, shape>`,
  but this conflicted with the less-than operator `<` when comparison operators were
  added to the language. The new syntax uses square brackets: `array[element_type, shape]`.
  This change makes the parser unambiguous and follows the convention used by many
  other programming languages for array declarations.


Upcoming features
=================

* `gauge` blocks:

  * support more than one out-spec

* `function` blocks:

  * support more than one {in & out}-spec

* `geometry` block:

  * re-introduce the `read_geometry_from_file` statement in the `geometry` block

  * extend the `nodes` statement, to allow selection of nodes based on
    arbitrary conditions (which produce a `bool` result, based on expressions
    involving the node coordinates); this would allow us to specify shapes
    such as spheres and cylinders within the GeLB files
