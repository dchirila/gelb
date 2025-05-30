# Future features for GeLB

In order to release a first version of the GeLB language & compiler faster, some
features had to be de-prioritized.
However, they are still very pertinent, and worthy of future consideration.

## Language Features

### Array selection assignment statements

- Implement `array_selection_assignment_stmt` in the grammar (currently commented out in `block_stmt` rule)
- This would allow direct assignment to array element selections, e.g.:
  ```
  my_array[0:10, 5] = 42;
  my_array[i, j:j+5] = some_expr;
  ```
- Would complement existing assignment statements:
  - `variable_assignment_stmt` (for scalar variables)
  - `lattice_out_selection_assignment_stmt` (for lattice outputs)
- Implementation notes:
  - Grammar rule is already sketched in GeLB.g4 line 55 (commented out)
  - Would need corresponding AST node class
  - Would need visitor implementation in ASTBuilderVisitor

## Input / Output (I/O)

- Test & enable compression for HDF5 / NetCDF files:
  - can significantly improve the daily "quality of life" of users
  - need to test with different compression methods & levels, to ensure that:
    - files can be written & read on all platforms
    - compression does not slow down the simulations significantly
