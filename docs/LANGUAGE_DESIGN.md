# GeLB Language Design Decisions

This document captures important design decisions made during the development of the GeLB language. Understanding these decisions helps contributors and users comprehend why certain features work the way they do.

Many of these decisions represent changes from the original GeLB specification in the PhD thesis. For historical context and rationale, see the relevant sections below.

## Guiding Principle: Familiarity Without Baggage

Many GeLB users will arrive from other LBM frameworks (lbmpy, Palabos,
OpenLB, waLBerla). GeLB should not surprise them: they should be able to
keep the same — or only slightly adjusted — mental model, presented as a
simpler language in which that mental model aligns directly with an
explicit view of the algorithms, with no complex class hierarchies to
reason about. At the same time, users genuinely new to LBM must never
need to learn the mechanics of *other* frameworks to understand GeLB:
framework-specific machinery does not leak into the language.

In practice this means: when a semantic question arises (e.g. "what do
masked solid cells' distribution functions hold?"), GeLB adopts the
explicit, documented version of what users of the major frameworks
already expect — rather than inventing novel semantics or leaving
behavior implicit in implementation details.

## Block Structure and Scope

### Constants in the lattices block

**Decision**: Constants are NOT allowed directly in the `lattices` block.

**Rationale**: This maintains a clear separation of concerns:
- The `lattices` block is exclusively for lattice declarations (instantiations)
- Each block type has a single, well-defined purpose
- This makes the code structure clearer and more predictable

**Where to define constants instead**:
- **Global constants**: In the `global_constants` block (accessible throughout the program)
- **Local constants**: Inside `initializer`, `dynamic`, or `gauge` blocks (scoped to that block)

**Example**:
```gelb
// Correct: Global constant
global_constants {
    const real D = 2.0;
}

lattices {
    lattice f(D, 9, real64, {64, 64}, {true, true});  // Can use global constant D
}

// Incorrect: Would cause a parser error
lattices {
    const real D = 2.0;  // NOT ALLOWED - constants cannot be defined here
    lattice f(D, 9, real64, {64, 64}, {true, true});
}
```

## Array Syntax

### Square brackets vs angle brackets

**Decision**: Array types use square brackets `array[type, shape]` instead of angle brackets `array<type, shape>`.

**Rationale**: 
- The angle bracket syntax conflicted with the less-than operator `<` when comparison operators were added to the language
- Square brackets are more commonly used for array declarations in other languages
- This makes the parser unambiguous

**Example**:
```gelb
// Current syntax (with square brackets)
const array[real, {3, 3}] identity = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};

// Old syntax from PhD thesis (would conflict with < operator)
// const array<real, {3, 3}> identity = {{1, 0, 0}, {0, 1, 0}, {0, 0, 1}};
```

### Element type and shape are coupled

**Decision**: `array[T, shape]` couples the element type `T` and the
`shape` into a single nominal type — there are no generics, no shape
polymorphism, and no separation between "an array of T" and "an array
of shape S".

**Rationale**: GeLB's role is to compile to high-performance Fortran
where every array has a fixed element kind and a fixed shape known at
compile time. Generic / shape-polymorphic types would require runtime
dispatch or template-style monomorphization, neither of which fits
GeLB's "transparent translation to Fortran" model.

**Practical limitation**: A function cannot be written generically over
shape — each shape needs its own function. For LBM use cases this is
not a limitation in practice, since the Q-value of a velocity set is
always known at compile time.

### Array shapes must be compile-time-foldable

**Decision**: The `shape` argument of `array[T, shape]` must be a
compile-time-foldable expression. The compiler accepts:

- An integer literal (`9`, `27`)
- An array literal of integer literals (`{3, 3}`, `{2, 3, 4}`)
- A reference to a global `const` declared with an integer expression
- An arithmetic expression composed of any of the above

```gelb
const int Q = 9;
const int N = 64;

// All valid: shape is compile-time-foldable
const array[real, 9]      EX = {0.0, 1.0, ...};
const array[real, Q]      EY = {0.0, 0.0, ...};
const array[real, {Q, Q}] M  = {{...}};
const array[real, Q + 1]  big = {...};

// NOT valid: shape uses a runtime variable
function MakeArray(int n) -> (array[real, n] arr) { ... }
//                                        ^
// 'n' is a runtime parameter, not a compile-time constant.
```

**Rationale**: Generated Fortran arrays have fixed extents declared at
compile time. Allowing a runtime shape would require either dynamic
allocation (out of scope for GeLB v1) or template-style monomorphization
(also out of scope).

**How it works internally**: Constant folding runs before type
inference, so by the time array shapes are checked, every valid shape
expression has been collapsed to an `IntLiteral_N` or
`Array1DLiteral_N` of int literals. Anything that hasn't been collapsed
is rejected with a type error.

## String Literals

### Strings not allowed in expressions

**Decision**: String literals (`STRING_LITERAL`) are intentionally excluded from expressions.

**Rationale**:
- Keeps the language simpler and more focused on numerical computations
- Strings are only needed in specific contexts (like simulation descriptions)
- Avoids complexity of string operations, concatenation, etc.

**Where strings can be used**:
- Only in the `simulation_description` statement

**Example**:
```gelb
// Correct: String used in simulation_description
simulation_description("2D Taylor-Green vortex simulation");

// Not supported: Strings cannot be used in expressions or assignments
// description = "some text";  // Would cause parser error
```

## Numeric Literals

### Non-negative literals only

**Decision**: The lexer only recognizes non-negative integer and real literals. Negative numbers are created using the unary minus operator.

**Rationale**:
- **Avoids lexer ambiguity**: In expressions like `x-3`, it's clear this is `x minus 3`, not `x followed by -3`
- **Standard practice**: Used by C, Java, Python, and most other languages
- **Simpler lexer**: No need for complex lookahead rules
- **Consistent operator handling**: Unary minus works the same as other unary operators

**Implementation**:
- Lexer tokens: `NON_NEGATIVE_REAL_LITERAL` and `NON_NEGATIVE_INT_LITERAL`
- Parser handles negation through `unaryExpr` rule
- `-3.14` is parsed as `(UnaryMinusExpr (RealLiteral 3.14))`

**Examples**:
```gelb
// These are all valid:
x = 3.14;        // Positive literal
y = -3.14;       // Unary minus applied to positive literal
z = x - 3.14;    // Binary minus (subtraction)
w = -(a + b);    // Unary minus applied to expression

// AST representation:
// -3.14 becomes: (UnaryMinusExpr (RealLiteral 3.14))
// x-3.14 becomes: (Sub (Identifier x) (RealLiteral 3.14))
```

## Assignment Statements

### Array selection assignments (Future consideration)

**Decision**: Direct assignment to array element selections (e.g., `my_array[0:10, 5] = 42;`) is not yet implemented.

**Rationale**:
- Prioritized getting core functionality working first
- The grammar rule `array_selection_assignment_stmt` is sketched but commented out
- Will be added in future versions to complement existing assignment types

**Current assignment types**:
- `variable_assignment_stmt` — scalar variables
- `lattice_out_selection_assignment_stmt` — lattice output selections
- `destructuring_assignment_stmt` — multi-target assignment from a function call or 1D array (see below)

### Destructuring assignment

**Decision**: The `{a, b, c} = expr;` syntax binds multiple targets in
a single statement. The RHS may be either:

1. **A multi-output user function call**, where the number of
   outputs matches the number of targets:

   ```gelb
   function Macro(array[real, 9] fIn) -> (real rho, real ux, real uy) {
       rho = sum(fIn);
       ux  = dot_prod(EX, fIn) / rho;
       uy  = dot_prod(EY, fIn) / rho;
   }

   {rho, ux, uy} = Macro(f.in[x, y | :]);
   ```

2. **Any 1D-array expression** whose statically-known length matches
   the number of targets — array literals, global constants of array
   type, lattice DF slices, etc.:

   ```gelb
   const array[real, 3] EX = {1.0, 2.0, 3.0};

   real a;
   real b;
   real c;
   {a, b, c} = EX;            // a = 1.0, b = 2.0, c = 3.0
   {a, b, c} = {7.0, 8.0, 9.0};
   ```

**Rules**:
- The RHS array length must be a **compile-time constant**, and must
  match the number of targets exactly. A mismatch is a frontend type
  error.
- All targets must share the same scalar type as the array elements.
  Mixed-type destructuring (e.g. `{int_a, real_b} = {1, 2.5}`) is not
  supported in v1; use explicit casts on the RHS elements
  (`{a, b} = {1.0, real(2)}`) if needed.
- Only **1D arrays** can be destructured. 2D-and-higher destructuring
  is out of scope for v1.

**Implementation note**: For function-call destructuring, the inliner
expands the function body inline with the targets bound directly. For
array-literal destructuring, each target gets the corresponding
element as a constant. For non-literal array RHS (variable, slice,
expression), the backend uses Fortran's `associate` construct to bind
the result to a temporary alias once and read element-wise from it,
avoiding repeated evaluation of the expression.

## File and Program Naming

### GeLB vs GD naming

**Decision**: Use "GeLB" consistently throughout, not "GD" (GeLB Description).

**Rationale**:
- No reason to burden users with two acronyms
- The `.gd` file extension is already taken by other programming languages
- Simplifies documentation and reduces confusion

**Result**: 
- Files are called "GeLB programs" stored in "GeLB files" with `.gelb` extension
- The name is "GeLB" throughout the language, its files and its documentation; "GD" does not appear

### Simulation name from filename

**Decision**: There is no `simulation_name` statement.

**Rationale**:
- The filename is used as the simulation name automatically
- Reduces boilerplate code
- Makes the language more consistent
- One less thing for users to worry about

## Version Management

### No gelb_version statement

**Decision**: There is no `gelb_version` statement.

**Rationale**:
- No plans to remove features from the language (backward compatibility)
- Forcing users to type this is pointless
- Simplifies the compiler
- Users have one less thing to worry about

**Future consideration**: Warn users if they're using an older compiler version that might not support newer features.

## Geometry and Node Selection

### Rectangular selections and predicate paints

**Decision**: In the `geometry` block a cell is painted either by a
rectangular selection with constant, inclusive bounds,
`nodes[lo:hi, ...] = CLASS;` (a single cell is `nodes[x0, y0] = CLASS;`),
or by a *predicate paint*, `nodes[where condition] = CLASS;`, whose
`bool` condition is evaluated once per cell at compile time with the
implicit coordinates (`x`; `x, y`; `x, y, z`, by rank) bound to that
cell. The condition may use constants, dimension constants, the scalar
math intrinsics, numeric conversions and pure single-output user
functions; it may not read a lattice, the time step `t` or `random()`.
The coordinates are available only inside a `where` condition.

Ordinary and predicate paints execute in their mutual source order and
a later paint wins whatever its kind. Every backend that materializes
the class map at run time replays the resolved paints in that order
(`ResolvedGeometry.paint_ops`), so validators and generated code agree
on one map.

**Rationale**:
- `where` keeps the predicate distinct from a point paint in every
  dimensionality, and the expression form is the one that can later
  take `t`, lattice values and global variables without new syntax;
  a form such as `nodes[F(:, :, ...)]` would have nowhere to put them.
- In this version the geometry is fixed for the whole run.

**Reserved words**: `enter`, `leave`, `reduce`, `reduction`, `update`,
`global_variables`, `transition` and `zone` are reserved for later
language stages and cannot be used as identifiers; none of them is an
implemented feature.

**Note**: `nodes` is equivalent to `node_range` from the thesis. The
`read_geometry_from_file` statement still needs more testing.

### Border repainting

**Decision**: The `border()` geometry statement repaints boundary cells
of one node class as another.

**Syntax**: `border(SOURCE) = TARGET;` — after all paints, repaints the
cells of SOURCE that have at least one in-domain axis-aligned neighbor
(the `2*d` face neighbors: ±1 in any dimension; diagonals are not
inspected and periodic seams are not crossed) of a different class as
TARGET. Interior cells remain as SOURCE: the rule repaints the source's
inner boundary, not an outer ring. Border rules execute in their own
source order, even when written between paints; each reads one
snapshot of the map and applies its replacements simultaneously, and a
later rule sees the previous rule's result. In this version a border
is applied once, when the geometry is resolved.

**Rationale**:
- Eliminates manual ±1 offset arithmetic for obstacle boundaries
- Reduces the common 3-class pattern (FLUID + WALL + SOLID with two
  rectangular selections) to a single paint + border statement
- Less error-prone than hand-computed boundary/interior regions

**Example**:
```gelb
// Before: fragile manual offset calculation
nodes[OX - R:OX + R, OY - R:OY + R] = WALL;
nodes[OX - R + 1:OX + R - 1, OY - R + 1:OY + R - 1] = SOLID;

// After: paint region + automatic border detection
nodes[OX - R:OX + R, OY - R:OY + R] = SOLID;
border(SOLID) = WALL;
```

### Masked node classes

**Decision**: A node class can be marked `masked` to indicate that its
cells are skipped at runtime and NaN-filled in the gauge output.

**Syntax**: The `masked` keyword appears after the closing parenthesis
of `node_class`. Three forms are allowed:

```gelb
node_class SOLID() masked;                    // pure-solid marker
node_class STATIC_SOLID(Init) masked;         // init only
node_class WALL(Init, BounceBack) masked;     // init + dynamic
```

**Constraint (enforced by the grammar)**: Masked node classes **cannot
have a gauge**. There is no 3-argument masked variant. Attempting to
write `node_class WALL(Init, Dyn, Gauge) masked;` is a parse error.

**Rationale**:
- Masked cells are skipped during the gauge sweep at runtime
- The output positions for masked cells are NaN-filled (via
  `ieee_value(0.0d0, ieee_quiet_nan)`)
- A per-cell gauge on masked cells would never run, so the syntax
  would be misleading

**Use cases**:
- Solid obstacles (interior cells where no LBM update is needed)
- Cells outside the simulation domain in non-rectangular regions

The combination with `border()` is particularly useful: paint the
entire obstacle as `SOLID() masked;`, then `border(SOLID) = WALL;`
automatically extracts the wall layer that runs bounce-back.

### Masked cells hold zero distribution functions (language guarantee)

**Decision**: The DFs of every masked-NC cell are explicitly zeroed
(in both ping-pong buffers, in every lattice) before the initializers
run. A masked node class *with* an initializer (e.g.
`STATIC_SOLID(Init) masked`) can still overwrite the zeros — the
zero-init runs first.

**Rationale**: a masked cell's neighbours may legitimately read its
DFs — the canonical case is a bounce-back `WALL` ring around a masked
`SOLID` obstacle gathering populations via `bounce_back_dfs`. Zero
populations contribute zero mass, so the read is harmless **iff** the
values are zero. This is the *full-way bounce-back* convention familiar
from other frameworks (Palabos explicitly zeroes populations in its
`Cell` constructor; OpenLB documents per-material initialization as
part of setup), made explicit in GeLB's generated code rather than
inherited from how the host happens to fill fresh memory. Each backend
emits the zeroing visibly: loop nests over the masked regions
(`cpu_fortran_serial`, `cpu_highway`) or a one-time
`gelb_masked_zero_init` kernel (`gpu_cuda_cpp`).

**Compiler enforcement**: the cross-NC coverage validator checks, at
compile time, that every DF a node class reads from a *neighbour* cell
is actually written by the neighbour's node class — with masked
neighbours exempt precisely because of the zero guarantee above. A
gauge reading a lattice its own node class never writes is likewise a
compile error. No population is ever read undefined.

**Related invariant — ghost cells**: halo (ghost) cells on *periodic*
axes are rewritten by the halo update before every timestep; ghost
cells on *non-periodic* axes are **never read** by generated code
(wall-adjacent reads clamp at the read site instead). Neither is
covered by the zero guarantee — and deliberately so: under
`gelbc --poison-uninit` (which fills lattice allocations with NaN to
detect reads of undefined cells) the non-periodic ghost layers stay
poisoned, so any future emission bug that reads them is caught
immediately. With the masked-cell guarantee in place, a program whose
output differs between a normal run and a `--poison-uninit` run is
reading genuinely undefined memory — a compiler bug worth reporting.

### Multiple initializers per node-class

**Decision**: Allow more than one `initializer` for each node-class.

**Rationale**:
- Avoids imposing unnecessary constraints on users
- More flexible than the thesis version (which allowed only one)

### Lattice size and periodicity location

**Original Design Decision (PhD thesis)**: Size and periodicity were to be specified in the `geometry` block using `set_grid_size` and `set_grid_periodicity` statements.

**Current Implementation**: Size and periodicity are specified during lattice instantiation (in `lattices` block), not in `geometry` block.

**New Syntax**:
```gelb
lattices {
  // 1D example
  lattice f(1,        // d: dimensionality
            1,        // q: number of discrete velocities  
            int,      // df_type: distribution function type
            32,       // grid_size: can be int or array {Nx} for 1D
            false     // periodicity: can be bool or array {periodic_x} for 1D
  );
  
  // 2D example
  lattice g(2, 9, real, {64, 32}, {true, false});
  
  // 3D example  
  lattice h(3, 27, real, {64, 64, 32}, {true, true, false});
}

geometry {
  // Simplified - only assigns node classes
  nodes[:] = BULK;     // 1D
  nodes[:,:] = BULK;   // 2D
  nodes[:,:,:] = BULK; // 3D
}
```

**Rationale for the change**:
- **Logical cohesion**: Grid size and periodicity are inherent properties of the lattice structure, not the geometry
- **Self-contained lattice definitions**: All lattice properties (dimensions, velocities, data types, size, periodicity) in one place
- **Better separation of concerns**: Geometry block focuses solely on node class assignment
- **Cleaner dependency flow**: Nx, Ny, Nz are derived from lattice definitions, not geometry
- **Consistency**: Aligns with the principle that each block has a single, well-defined purpose

**Migration notes**:
- This is a breaking change from the older PhD-thesis syntax
- Programs that still use `set_grid_size` or `set_grid_periodicity` should move
  those values into the `lattice` declaration
- For GeLB v1, all lattices must have identical grid_size and periodicity

## Lattice Access Separator (`|`)

### The `|` in `f.out[x, y | :]`

**Decision**: Use `|` (vertical bar) to separate spatial indices from the
distribution function (DF) range in lattice access expressions.

**Rationale**: In kinetic theory, the distribution function `f(x, v)` lives
in **phase space** — position × velocity. The `|` literally separates the
spatial coordinates (left) from the velocity/DF dimension (right), mirroring
the mathematical notation where position and velocity are distinct index
groups. For LBM practitioners, this mapping is natural.

**Examples**:
```gelb
f.out[x, y | :]     // All DFs at site (x, y)
f.in[x, y | 0]      // Single DF (index 0) at site (x, y)
f.out[x, y | 1:3]   // DF slice (indices 1 through 3)
```

**Reserved status**: `|` is permanently reserved for this purpose. It will
**not** be reused for bitwise operators or union types. GeLB does not need
bitwise operators — it is a domain-specific language for numerical simulation,
not a systems programming language.

## Lattice Read/Write Semantics (`f.in` / `f.out`)

### The two-timestep illusion is a language guarantee

**Decision**: GeLB guarantees, as a **language-level contract**, that
inside any single `dynamic` block:

- `f.in[...]` always reads from the **previous timestep's** lattice
  state (the "old" data, frozen for the duration of the timestep).
- `f.out[...]` always writes to the **next timestep's** lattice state
  (the "new" data, not yet visible to anyone).
- These two timesteps are **distinct, non-overlapping** logical
  snapshots of the lattice. A read from `f.in[...]` cannot observe a
  write from `f.out[...]` made earlier in the same timestep —
  *anywhere* on the grid, by any worker, in any order.

This is true regardless of:
- The order in which cells are processed within a timestep
- Whether cells are processed sequentially, in parallel (OpenMP),
  on a GPU, or in any other order a future backend may choose
- Whether the user reads neighboring cells (`f.in[x-1, y | 3]`) or
  the local cell (`f.in[x, y | :]`)

**Why this matters**: LBM streaming reads from neighbors, and any
shared-memory parallel implementation that overwrote `f.in` cells
in-place would corrupt those reads. The classical implementation
technique is **ping-pong (double-buffer) lattices**: keep two copies
of the lattice and swap their roles each timestep. GeLB's reference
backends use exactly this technique.

But the **user should not have to know this**. GeLB exposes the clean
abstraction "previous timestep / next timestep" as part of the
language contract, just like a modern CPU exposes the illusion of
sequential execution while internally reordering instructions,
predicting branches, and speculating across barriers. The user writes
code against the simple model; the backend may use any technique it
likes (ping-pong buffers today, esoteric-twist or AA-pattern in-place
streaming tomorrow) as long as the contract is preserved.

**Concrete consequences**:
- Pull-streaming dynamics that read from neighbors are safe by
  construction:
  ```gelb
  dynamic Stream {
      // Read from 9 different neighbors; all reads see the
      // previous timestep, none can race against this site's write.
      array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY});
      f.out[x, y | :] = collide(fIn);
  }
  ```
- The compiler is free to parallelize a `dynamic` block across cells
  with no synchronization, because no cell's `f.out` write can affect
  any other cell's `f.in` read within the same timestep.
- The same source compiles unchanged for serial CPU, OpenMP,
  CUDA, and any future SIMD/MPI/heterogeneous backend.

**For GeLB developers (not part of the user contract)**: The current
backends implement this guarantee with a ping-pong (double-lattice)
buffer scheme. Each lattice array has a trailing `0:1` dimension that
selects "old" vs "new"; the indices are swapped at the end of each
timestep. Future backends are free to drop the second copy in favor of
in-place techniques like the **esoteric twist** or the **AA pattern**,
which exploit knowledge of the streaming stencil to overwrite cells
safely without a second buffer. From the user's perspective, the only
observable difference will be performance — never correctness.

## Lattice Operations vs Math Intrinsics

GeLB's intrinsic functions fall into two categories that look the
same syntactically but have different semantics.

### Math intrinsics (the usual kind)

These are stateless mathematical functions that take expression
arguments and return a value:

```gelb
real s = sin(x);
real d = sqrt(a*a + b*b);
real m = mod(i, n);
array[real, 3] s = sum(matrix);
```

They include `sin`, `cos`, `tan`, `tanh`, `sqrt`, `exp`, `log`, `abs`,
`min`, `max`, `mod`, `atan2`, `sum`, `dot_prod`, `random`, `matmul`,
`transpose`, `inverse`, `determinant`. The compiler treats them
exactly like regular function calls.

### Lattice operations (`upstream_dfs`, `bounce_back_dfs`)

`upstream_dfs(lat, x, y, {EX, EY})` and `bounce_back_dfs(lat, x, y,
{EX, EY})` *look* like intrinsic calls but have **special semantics**:

- The first argument is **a lattice name**, not an expression. The
  compiler binds it as a lattice reference, not as a value to evaluate.
- The middle arguments are the **current cell coordinates** (the
  implicit `x`, `y`, `z` variables). They are *not* evaluated as
  general expressions; the compiler reads them positionally.
- The last argument is the **velocity set** as compile-time integer
  arrays (e.g. `{EX, EY}` where `EX` and `EY` are global constants).
  The compiler reads the constant values to compute streaming
  offsets at code-generation time.

The result is an `array[real, q]` constructed by gathering the right
distribution functions from neighboring cells:

- `upstream_dfs` performs **pull streaming**: for DF index `i`, it
  reads `f.in[x - EX[i], y - EY[i] | i]` (with periodic wrapping).
- `bounce_back_dfs` performs **bounce-back**: for DF index `i`, it
  reads `f.in[x + EX[i], y + EY[i] | opp(i)]`, the population of the
  neighbour in direction `i` that points back at this cell, where
  `opp(i)` is the index whose velocity is the negation of velocity
  `i`. The fluid neighbour pulls it on the next step as its slot `i`
  (full-way bounce-back, the wall midway between the nodes). A link
  leaving a non-periodic grid gives the cell's own
  `f.in[x, y | opp(i)]`, which nothing streams.

These are *the* canonical LBM streaming operations, baked into the
language because expressing them with manual per-DF reads would be
tedious and stencil-extraction would have to recover the pattern.

```gelb
dynamic Stream {
    // Pull-stream all 9 DFs from upstream neighbors in one operation:
    array[real, 9] fIn = upstream_dfs(f, x, y, {EX, EY});
    f.out[x, y | :] = collide(fIn);
}

dynamic BounceBack {
    // Send every arriving population back along its link
    // (full-way bounce-back wall):
    f.out[x, y | :] = bounce_back_dfs(f, x, y, {EX, EY});
}
```

**Why expose these as intrinsics rather than letting users write them
manually?** The compiler reads the velocity set at code-generation
time, computes per-DF offsets and the opposite-DF mapping, and emits
straight-line Fortran array constructors. A hand-written equivalent
would force the user to repeat the velocity set as numeric literals
in every dynamic block, and the compiler's stencil analysis would
have to reverse-engineer the pattern.

### Type-cast intrinsics (`int(x)`, `real(x)`, ...)

GeLB exposes nine type-cast intrinsics, one per scalar type:

- **Integer**: `int(x)`, `int8(x)`, `int16(x)`, `int32(x)`, `int64(x)`
- **Floating-point**: `real(x)`, `real16(x)`, `real32(x)`, `real64(x)`

Each accepts any numeric or boolean argument and returns the converted
value (preserving the argument's shape — casts work element-wise on
arrays). Casts let users opt into **lossy downcasts** that the
implicit-promotion system rejects:

```gelb
const real PI = 3.14;
const int  N  = int(PI);        // 3 — explicit truncation, accepted
// const int  N  = PI;          // ERROR: implicit real → int rejected

real density = 1.0;
int8 count   = int8(density);   // narrow to 1-byte int

bool flag = true;
int  value = int(flag);         // 1
```

**Truncation rule**: `real → int` casts truncate toward zero
(matching Fortran's `int()` intrinsic and C's `(int)` cast):

| Input  | `int(x)` |
|--------|----------|
| `3.7`  | `3`      |
| `-3.7` | `-3`     |
| `0.99` | `0`      |

**Bool conversion**: `true → 1`, `false → 0` for both `int()` and
`real()` casts.

**Compile-time evaluation**: Casts on constant arguments are folded
during the constant-folding pass, so `const int N = int(3.14);` is
equivalent to `const int N = 3;` in the generated code.

**Implementation note**: The cast intrinsics share their backend
emission with the implicit type-promotion mechanism (via the internal
`_emit_cast` helper). Adding a new scalar type to GeLB therefore only
requires extending the cast helper once — the corresponding intrinsic
will work automatically.

## Syntax Conventions

### Function parameters and named results

**Decision**: A function signature consists of a comma-separated
parameter list followed by an arrow and a parenthesized list of named
results:

```gelb
function Macro(array[real, 9] fIn)
        -> (real rho, real ux, real uy) { ... }
```

The parameter list is always present, including for a zero-input
function. Result parentheses are required even for one result. A gauge
cannot take parameters, so it starts directly with its named-result
clause:

```gelb
function Noise() -> (real value) { ... }
gauge Hydro -> (real rho, real ux, real uy) { ... }
```

Each parameter and result repeats its type and entries are separated by
commas, with no trailing comma. Functions and gauges must declare at
least one result. Result names are semantic: function and gauge bodies
assign to them, and multi-result function calls bind them positionally
through destructuring assignment.

**Rationale**:

- The signature resembles familiar parameter and return-type syntax
  without implying a `return` control-flow statement, which GeLB does
  not have.
- `->` makes the input/result boundary immediately visible while
  preserving named multi-result functions.
- Parentheses mean parameter or result lists; braces remain reserved for
  blocks, aggregate literals, and destructuring.
- The words `in` and `out` remain dedicated to lattice-buffer selectors
  such as `f.in[...]` and `f.out[...]`.
- The AST stores parameters and named results as ordered declaration
  lists, keeping type analysis and code generation independent of
  signature formatting.

### Const keyword syntax

**Decision**: Use `const` keyword prefix instead of `_const` suffix for constants.

**Rationale**:
- More natural syntax for programmers familiar with C-like languages
- Cleaner and more readable

**Examples**:
```gelb
// Current syntax
const real pi = 3.14;
const array[int, {2, 2}] I = {{1, 0}, {0, 1}};

// Old thesis syntax
// real_const pi = 3.14;
```

## Naming Conventions

### Block naming consistency

**Current state**: Every block's grammar rule carries the `_block` suffix (`global_constants_block`, `lattices_block`, `function_block`, `initializer_block`, `dynamic_block`, `gauge_block`, `node_classes_block`, `geometry_block`); the keyword a program writes is the name without the suffix.

## Block order flexibility

**Decision**: Allow users to specify blocks in any order they like.

**Rationale**:
- More flexible for users
- Different problems might have different natural orderings
- The compiler can handle any order

**Implementation note**: See GeLB.g4 line 7 comment.

## Expression Evaluation

### Operator precedence

**Decision**: Follow standard operator precedence from mainstream programming languages.

**Precedence order** (highest to lowest):
1. Parentheses, literals, identifiers, array/lattice selections
2. Power (`^`) - right associative
3. Unary operators (`+`, `-`, `!`)
4. Multiplication/Division (`*`, `/`)
5. Addition/Subtraction (`+`, `-`)
6. Comparison (`<`, `>`, `<=`, `>=`)
7. Equality (`==`, `!=`)
8. Logical AND (`&&`)
9. Logical OR (`||`)

**Rationale**:
- Matches conventions from C/C++, Python, Java, and FORTRAN
- Follows standard mathematical precedence
- Minimizes surprises for users coming from other languages
- No need to memorize GeLB-specific rules

**Examples**:
```gelb
// Mathematical precedence
2 + 3 * 4        // = 14 (not 20)
2 ^ 3 ^ 2        // = 512 (right associative: 2^(3^2) = 2^9)

// Comparison before logical
x > 5 && y < 10  // = (x > 5) && (y < 10)

// AND before OR
a || b && c      // = a || (b && c)

// Unary has high precedence
-x ^ 2           // = -(x^2), not (-x)^2
!a && b          // = (!a) && b
```

---

*This document will be updated as new design decisions are made or existing ones are clarified.*
