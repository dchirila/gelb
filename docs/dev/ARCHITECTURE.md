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

## Main abstractions / concepts of the GeLB language

TODO move this to User's Guide

### `lattice`(s): the main data-structure(s)

All GeLB programs are centered on (at least one) `lattice` data-structure. A
`lattice` is basically a (one-, two-, or three-dimensional) cartesian grid of
`node`s. Each `node` has a state-vector attached to it (the length of the
state-vector being a constant for the whole lattice). To use LB terminology,
each element of the state-vector represents a node-local distribution
function (DF), with *indexing starting at zero*. As we will discuss later,
each `node` will need to be assigned to a `node_class` (think of "painting"
the `lattice` using different colors).

#### `lattice` input/output (I/O) ports

When implementing LB algorithms using general-purpose programming languages
(GPLs), the `lattice` is typically a `(d+1)`-dimensional array (where `d`
stands for the number of dimensions of the simulated spatial domain, and the
`+1` comes from the `node`-local state-vector). The LB algorithm then
directly reads from and writes to this array. Unfortunately, an update-rule
of a `node` may overwrite DFs which are still needed by the update-rule at a
neighboring `node` (within the same time-iteration). Such data-dependencies
are quite common, and causing beginners (or even experts) much grief. Two solutions have emerged to deal with this problem:

1. The easiest solution (used by many LB implementations) is to simply use
two copies of the `lattice` (one holding the state at the current time-step,
and another for holding the state at the next time-step). To make things more
efficient, we can say that odd time-steps belong to one `lattice`, while even
time-steps belong to the other `lattice`. This approach certainly works, but
it can introduce other limitations:

   (a) As the amount of memory used by the simulation is doubled, the maximum
   size of the `lattice` that can be simulated is cut in half (because
   system/GPU memory is finite). 

   (b) Also, the increased memory usage of the simulation usually places
   additional stress on the memory subsystem, reducing the efficiency of
   caches. Although (in theory) we still read and write the same amount of
   data, from/to the memory, the way caches operate (in order to maintain
   data-consistency) means that doubling the memory footprint also generates
   more traffic on the memory bus. All this (usually) amounts to
   significantly longer simulation times, because modern computing hardware
   tends to be limited more by the volume of data transfers than by the
   number of arithmetic operations).

2. A more sophisticated approach is to orchestrate the updates of the DFs in
a very careful manner, so that we do not overwrite any data which will still
be needed. However, this approach introduces several problems:

   (a) **Difficult to understand, implement, and (especially) generalize**:
   While it is doable to find a clever sequence of DF-updates which is
   applicable to simple / idealized cases (periodic domains or simple BCs),
   these sequences quickly become un-applicable e.g. when a user decides to
   implement a more complex BC. In the worst case, the user may not even be
   aware of the underlying assumption, which can lead to incorrect
   simulations (which are arguably worse than slow simulations).

   (b) **Potential to introduce other performance "bugs"**: The core strength
   of modern computing hardware consists of the ability to perform parallel
   computations. For example, a common approach for GPUs is to assign each
   `node` to a compute-thread, and allow the hardware-scheduler to freely
   decide in which order and on which hardware compute-units to map these
   thread. Thus, if the prescribed sequence of DF-updates is not adapted to
   the actual hardware that runs the simulation, there is a real danger of
   under-utilizing the CPU/GPU/FPGA, by forcing (semi-)serialized update of
   the `node`s.
   
The core problem is that the computer (or a GPL compiler) has no easy way of understanding the data-dependencies. In GeLB, we make it easier to compute these dependency-graphs automatically, by:

1. Forcing all data-operations on the `lattice` to be *explicitly* assigned to
the *input* (`in`) port or to the *output* (`out`) port of the `lattice`.
A read/write DF access operation is assigned to one of these two ports by
simply appending the suffix `.in` or `.out` to the name of the `lattice`
instance. For example, assuming that we have a 2D `lattice` which we named
`f`, we would use:
   ```
   f.out[1, 1 | 0] = ...some expression...
   ```
   to write the new state (at time `(n+1)`) of DF 0 of the `node` at
   `(x, y) = (1, 1)`. Similarly, if a variable `alpha` depends on the current
   value of this DF (at time `n`), we would use:
   ```
   alpha = ...expression involving f.in[1, 1 | 0]...
   ```
   **IMPORTANT**: While we may read `f.in[...]` any number of times within a
   time-step, we can only write (assign) to `f.out[...]` of each DF **only
   once** during each time-step! This disallows the creative use of DFs as "scratch space" during an iteration. However, from the point of view of GeLB, such tricks are implementation details, which should be generated automatically (when possible) by the GeLB compiler, by analyzing the data-dependency graph.

2. Limiting which ports may be used for different classes of data-operations (as discussed in the next section).

By accepting the above-mentioned constraints enforced by the GeLB compiler,
the problem of generating a graph of data-dependencies becomes much more
tractable (compared to that faced e.g. by `C(++)` or `Fortran` compilers,
which always have to assume the worst cases, to ensure correctness).
   
### Working with the `lattice`

TODO-insert-Figure-18-p80-thesis (Initializer, Dynamic, Gauge)

After analyzing many LB code-samples (written by yours truly or by others),
three types of lattice operations were identified (each of them having a
correspondent in GeLB):

1. Before a simulation even begins, we want to initialize the DFs at each
`node` of the `lattice`, to impose some initial conditions (ICs). In GeLB
programs, this step is achieved by defining `initializer`s.

   For an `initializer`, the `lattice` is *write-only* (i.e. it is not
   allowed to read any DFs, because initially all DFs are assumed to be in an
   undefined state). Put otherwise, for a `lattice` named `f`, an
   `initializer` *may **not*** use `f.in[...]` values (the `input` port of
   the `lattice`).

   **IMPORTANT**: The limitation mentioned above (when we discussed the
   `input` and `output` ports of `lattice`s) is important here -- once a DF
   is written (by assigning a value to `f.out[...]` within the
   `initializer`), it
   **cannot be overwritten** (neither by the same `initializer`, nor by
   another one).

2. After the initialization phase, we enter a time-loop. During each
iteration, at each `node` of the `lattice` we apply a certain update-rule,
which computes the state-vector of the `node` at time `n+1`, based on the
state of the `node` (and perhaps also on the state of some neighboring
`node`s) at time `n`. In GeLB programs, such an update-rule is specified by
writing a `dynamic`.

   For a `dynamic`, the `lattice` is *read-write*, i.e. it can use both the `input` and the `output` ports (given a `lattice` named `f`, a `dynamic` may read `f.in[...]` values, and also write to `f.out[...]` values).

   **IMPORTANT**: Similar to an `initializer`, a `dynamic` may only write to
   `f.out[...]` **once** per time-step -- if we say that a certain DF will
   have some value at the next time-step, we cannot change our mind :).

3. Computing without output would be meaningless, of course. So, every few
time-iterations (or even at every iteration, or maybe just at the end of the
simulation), we want to create some output based on the state of the
`lattice`. In GeLB programs, such operations are specified by writing
`gauge`(s). For example, in a LB fluid-flow simulation, we may want to write
a `gauge` which evaluates the density at each `node`, and another which
evaluates the momentum (or even a single `gauge` which evaluates both
quantities, for greater efficiency). Within the body of a `gauge`, the
`lattice` is *read-only* (we can only use the `input` port, i.e. `f.in[...]`
for a `lattice` named `f`).


### `node_classes` and `geometry`

Another (trivial, but important) observation originating from analyzing many
LB implementations is that `node`s may be usually attributed to a finite (and
small) set of classes. For example, in a fluid flow problem where the fluid
is surrounded by solid (no-slip) walls, we may have one class for the `node`s
within the bulk of the fluid and another class for the wall `node`s.
Naturally, for simulations where we have to distinguish based on more ICs
and/or BCs, the number of `node` categories is larger; however, even for the
most demanding simulations, the number of different BCs is still rather
small.

Accordingly, GeLB requires users to *explicitly* define each `node_class`.
In GeLB terminology, a `node_class` is defined by the set of
`initializer`(s), `dynamic`(s) and `gauge`(s) which need to be applied for a
certain class of `node`(s). This idea is closely tied to the way we define
the `geometry` in GeLB -- the "paint" metaphor. When it comes to defining the
`geometry` for your simulation, you can think of a `lattice` as a "canvas",
where you are invited to "splash" different colors (`node_class`es) onto the
different `node`s in the `lattice`. Each "splash" corresponds to a
node-assignment command within the `geometry` block, such as:
```
nodes[1, :] = WALL;
```
where `WALL` is the name of a `node_class` defined by you in the
`node_classes` block. However, the analogy is not perfect -- unlike colors in
painting, **GeLB `node_class`es may NOT overlap**. You *can* "splash" more
than one `node_class` onto a `node`, but only the `node_class` assigned last
is retained (this property is useful when we want to assign most of a
sub-domain to a `node_class`, but then we want to re-assign some smaller
regions to different `node_class`es, e.g. to implement BCs).

TODO this is the only IF-condition (implicit) currently supported by GeLB programs.

### Closing and what comes next

Congratulations! You now have a pretty good idea about the structure of a GeLB program. Next, we will:
- show you some sample GeLB programs, after which
- we will got into more details about rules (what you may and may not write) in each type of block of your GeLB programs
- finally, we will discuss issues related to code-generation and running your simulations on actual systems.