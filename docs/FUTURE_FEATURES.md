# Future features for GeLB

In order to release a first version of the GeLB language & compiler faster, some
features had to be de-prioritized.
However, they are still very pertinent, and worthy of future consideration.

## Language Features

### Coordinate access in geometry blocks

- Allow using lattice coordinates (x, y, z) in geometry block expressions
- This would enable coordinate-based node painting patterns, e.g.:
  ```gelb
  nodes[:, y < 5] = WALL;           // Bottom wall
  nodes[x > Nx - 10, :] = OUTLET;   // Right outlet region
  nodes[x == 0, y == 0] = CORNER;   // Special corner treatment
  ```
- Current limitation: x, y, z are only available in initializer, dynamic, and gauge blocks
- Implementation considerations:
  - Would need to add implicit coordinate symbols to geometry block's symbol table
  - Must ensure coordinates are properly bounded by grid dimensions
  - Could enable more complex geometry specifications without external tools


## Compiler Optimizations

### Advanced Constant Folding

The basic constant folding optimization is implemented, but several advanced features remain for future implementation:

#### Cross-Statement Constant Propagation
- Propagate constant values across statement boundaries
- Example:
  ```gelb
  const int A = 5;
  const int B = A + 3;  // Should fold to B = 8
  ```
- Implementation considerations:
  - Requires tracking constant definitions across the symbol table
  - Must respect scoping rules and block boundaries
  - Could enable significant optimization in complex constant expressions

#### Dead Code Elimination Based on Constant Conditions
- Remove unreachable code when conditions can be evaluated at compile time
- Example:
  ```gelb
  if (true && false) {  // Constant folds to: if (false)
      // This code becomes unreachable and can be eliminated
  }
  ```
- Benefits:
  - Reduces generated code size
  - Eliminates unnecessary computations
  - Improves static analysis accuracy

#### Array and String Constant Folding
- Fold expressions within constant array literals
- Example:
  ```gelb
  const array[int, 3] data = {1+1, 2+2, 3+3};  // Fold to {2, 4, 6}
  ```
- Implementation considerations:
  - Must handle multi-dimensional arrays
  - Should preserve array structure and indexing
  - Could enable better array bounds analysis

#### Function Call Folding for Pure Functions
- Evaluate calls to pure (side-effect-free) functions at compile time
- Requirements:
  - Function purity analysis
  - Compile-time function evaluation
  - Integration with intrinsic function system

## Input / Output (I/O)

- Test & enable compression for HDF5 / NetCDF files:
  - can significantly improve the daily "quality of life" of users
  - need to test with different compression methods & levels, to ensure that:
    - files can be written & read on all platforms
    - compression does not slow down the simulations significantly
