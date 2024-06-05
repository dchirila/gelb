# Future features for GeLB

In order to release a first version of the GeLB language & compiler faster, some
features had to be de-prioritized.
However, they are still very pertinent, and worthy of future consideration.

## Input / Output (I/O)

- Test & enable compression for HDF5 / NetCDF files:
  - can significantly improve the daily "quality of life" of users
  - need to test with different compression methods & levels, to ensure that:
    - files can be written & read on all platforms
    - compression does not slow down the simulations significantly
