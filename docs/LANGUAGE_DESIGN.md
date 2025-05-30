# GeLB Language Design Decisions

This document captures important design decisions made during the development of the GeLB language. Understanding these decisions helps contributors and users comprehend why certain features work the way they do.

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

## Naming Conventions

### Block naming consistency

**Current state**: Some blocks use `_block` suffix (e.g., `global_constants_block`, `lattices_block`) while others don't (e.g., `initializer`, `dynamic`, `gauge`).

**Note**: This inconsistency exists for historical reasons and may be addressed in future versions for better consistency.

---

*This document will be updated as new design decisions are made or existing ones are clarified.*