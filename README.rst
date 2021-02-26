=========================================================
GeLB: GEneric Lattice Boltzmann framework from the future
=========================================================

GeLB is a framework which allows you to quickly create numerical simulations
based on the Lattice Boltzmann (LB) method, using a high-level description of
your simulation.

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

- Compiler for the GeLB description (GD) language, which allows you to quickly write simulations based on the lattice Boltzmann method (LBM) or finite differences (FD)

- Expressive and intuitive syntax

- Built-in sanity checks (at *compile-time*) which prevent many types of bugs common in LBM implementations

- Automatic generation of GPU code (using OpenCL)


Installation
============

Although we have tried to make GeLB as self-contained as possible, it *does*
depend on a fair number of libraries. The easiest way to install GeLB and all of
its dependencies is to use Anaconda.

* Install Anaconda (see instructions `here
  <https://www.anaconda.com/products/individual>`_)

* Open a terminal and perform the following steps:

  * Clone this repository:

    ``git clone https://github.com/dchirila/gelb.git``

  * Change to the directory containing the local copy of the repository

    ``cd git``

  * Create ``conda`` environment from ``gelb.yml``:

    ``conda env create --file gelb.yml``


Limitations of the GD language
==============================

Compared to most general-purpose languages (GPLs), the GD language imposes
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
fragmentation of the language (and to ensure that GD programs are easily
interchangeable), we encourage you to submit a GitHub pull request (PR) if you
have implemented a feature which would be useful to the rest of the community.
Contributors are strongly encouraged to also read the *GeLB developer manual*.

Among the most notable restrictions, we mention:

- No `print` statement. The only way to generate output from a GD program is to
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

    In other words, GD functions work similar to functions in mathematics (no
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



Revisions w.r.t. my PhD thesis
==============================

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

  * `const array<int, {2, 2} I = {{1, 0}, {0, 1}};` to declare and initialize a
    constant array of integers.


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
    such as spheres and cylinders within the GD-files
