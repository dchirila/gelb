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


## Input / Output (I/O)

- Test & enable compression for HDF5 / NetCDF files:
  - can significantly improve the daily "quality of life" of users
  - need to test with different compression methods & levels, to ensure that:
    - files can be written & read on all platforms
    - compression does not slow down the simulations significantly
