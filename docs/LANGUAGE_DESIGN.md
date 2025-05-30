# GeLB Language Design Decisions

This document captures important design decisions made during the development of the GeLB language. Understanding these decisions helps contributors and users comprehend why certain features work the way they do.

Many of these decisions represent changes from the original GeLB specification in the PhD thesis. For historical context and rationale, see the relevant sections below.

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
    lattice f(d=D, q=9, df_type=real64);  // Can use global constant D
}

// Incorrect: Would cause a parser error
lattices {
    const real D = 2.0;  // NOT ALLOWED - constants cannot be defined here
    lattice f(d=D, q=9, df_type=real64);
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
- `variable_assignment_stmt` - for scalar variables
- `lattice_out_selection_assignment_stmt` - for lattice output selections

## File and Program Naming

### GeLB vs GD naming

**Decision**: Use "GeLB" consistently throughout, not "GD" (GeLB Description).

**Rationale**:
- No reason to burden users with two acronyms
- The `.gd` file extension is already taken by other programming languages
- Simplifies documentation and reduces confusion

**Result**: 
- Files are called "GeLB programs" stored in "GeLB files" with `.gelb` extension
- All mentions of "GD" have been replaced with "GeLB"

### Simulation name from filename

**Decision**: The `simulation_name` statement is no longer required.

**Rationale**:
- The filename is used as the simulation name automatically
- Reduces boilerplate code
- Makes the language more consistent
- One less thing for users to worry about

## Version Management

### No gelb_version statement

**Decision**: Programs no longer need to include a `gelb_version` statement.

**Rationale**:
- No plans to remove features from the language (backward compatibility)
- Forcing users to type this is pointless
- Simplifies the compiler
- Users have one less thing to worry about

**Future consideration**: Warn users if they're using an older compiler version that might not support newer features.

## Geometry and Node Selection

### Rectangular selections only

**Decision**: In the `geometry` block, only rectangular node-selections are allowed using the `nodes` statement.

**Rationale**:
- The `node` statement is not needed (it's just a special case of `nodes`)
- The `read_geometry_from_file` statement needs more testing
- Keeps the initial implementation simpler

**Note**: `nodes` is equivalent to `node_range` from the thesis.

### Multiple initializers per node-class

**Decision**: Allow more than one `initializer` for each node-class.

**Rationale**:
- Avoids imposing unnecessary constraints on users
- More flexible than the thesis version (which allowed only one)

### Lattice size and periodicity location

**Decision**: Size and periodicity are specified during lattice instantiation (in `lattices` block), not in `geometry` block.

**Rationale**:
- More natural to specify these properties with the lattice
- Allows different lattices to have different sizes and periodicity traits
- Better separation of concerns

## Syntax Conventions

### Parentheses for specifications

**Decision**: `gauge` out-specs and `function` in/out-specs use parentheses instead of square brackets.

**Rationale**:
- Brings syntax closer to other programming languages
- More familiar to programmers

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

**Current state**: Some blocks use `_block` suffix (e.g., `global_constants_block`, `lattices_block`) while others don't (e.g., `initializer`, `dynamic`, `gauge`).

**Note**: This inconsistency exists for historical reasons and may be addressed in future versions for better consistency.

## Block order flexibility

**Decision**: Allow users to specify blocks in any order they like.

**Rationale**:
- More flexible for users
- Different problems might have different natural orderings
- The compiler can handle any order

**Implementation note**: See GeLB.g4 line 7 comment.

---

*This document will be updated as new design decisions are made or existing ones are clarified.*