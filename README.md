![GitHub all releases](https://img.shields.io/github/downloads/dchirila/gelb/total?logo=GitHub&style=flat-square)
[![Website](https://img.shields.io/website?logo=Read%20The%20Docs&style=flat-square&url=https%3A%2F%2Fgelb-lang.org)](https://gelb-lang.org)
[![Twitter Follow](https://img.shields.io/twitter/follow/gelb12410715?label=GeLB-lang&style=social)](https://twitter.com/gelb12410715)

<p align="center">
    <img
    src="./docs/figs/gelb_logo.svg"
    width="200"
    alt="GeLB logo">
</p>

# GeLB: Generic Lattice Boltzmann Framework

GeLB is a domain-specific programming language (DSL) and compiler framework for creating high-performance numerical simulations based on the Lattice Boltzmann Method (LBM) and finite differences (FD).

## Features

- **Easy to learn**: Intuitive syntax designed for LBM researchers and practitioners
- **Compile-time validation**: Built-in correctness checks prevent common LBM implementation bugs
- **High performance**: Automatic optimization and parallelization (coming soon)
- **Type safety**: Advanced type system with compile-time range validation
- **Extensible**: Open-source framework with clean architecture
- **Multiple backends**: Currently supports Fortran, with GPU OpenCL planned

## Core Concepts

GeLB programs revolve around four fundamental abstractions:

1. **Lattices**: Multi-dimensional arrays storing distribution functions
2. **Initializers**: Blocks for setting initial lattice values  
3. **Dynamics**: Blocks for lattice update operations (read and write)
4. **Gauges**: Blocks for reading values from lattices for output

Additional concepts include:
- **Node Classes**: Define behavior for different simulation node types
- **Geometry**: Spatial assignment of node classes to grid points
- **Global Constants**: Compile-time constants for simulation parameters

## Language Philosophy

GeLB is a **hybrid language** combining:
- **Imperative operations**: Expressions and assignments for lattice operations
- **Declarative specifications**: High-level descriptions of simulation structure

Key design principles:
- **Pure functions only**: No side effects for predictable parallelization
- **No traditional control flow**: No if/while/switch statements - use intrinsic functions and node classes instead
- **No print statements**: All output through Gauges for consistency
- **Automatic parallelization**: Users don't specify parallelization details

## Current Implementation Status

### ✅ Frontend (98% Complete)
- ANTLR4-based parser with full grammar support
- Complete AST construction with visitor pattern
- Sophisticated type inference system
- Hierarchical symbol tables with scoping
- Compile-time constant folding and validation
- Range resolution and validation
- Intrinsic functions: `sum()` and `dot_prod()` implemented

### ✅ Midware (Core Complete)
- AST optimization passes
- Constant folding and propagation
- Division by zero validation
- AST validation for backend consumption

### 🚧 Backend (In Development)
- CPU Serial Fortran backend (primary target) - skeleton implemented
- GPU OpenCL backend - planned
- OpenMP parallel backend - planned

## Installation

GeLB uses `uv` for Python package management and requires Python 3.12.7+.

### Quick Start

1. **Setup the development environment**:
   ```bash
   # On Unix/MacOS:
   ./scripts/gelb_bootstrap.sh
   
   # On Windows:
   .\scripts\gelb_bootstrap.ps1
   ```

2. **Activate the virtual environment**:
   ```bash
   # On Unix/MacOS:
   source .venv/bin/activate
   
   # On Windows:
   .\.venv\Scripts\activate
   ```

3. **Install GeLB in development mode**:
   ```bash
   uv pip install -e .
   ```

4. **Run the compiler**:
   ```bash
   uv run python gelbc.py examples/basic/1d/ex0_int_vec_setto_one.gelb
   ```

### Optional: Clean Generated Files
```bash
# On Unix/MacOS:
./scripts/cleanup_repo.sh

# On Windows:
.\scripts\cleanup_repo.ps1
```

## Example GeLB Program

```gelb
simulation_description("2D Lid-driven cavity flow");

global_constants {
    const int Nx = 128;
    const int Ny = 128;
    const real TAU = 0.6;
    const real U_LID = 0.1;
}

lattices {
    lattice f(d=2, q=9, df_type=real);
}

initializer InitEquilibrium {
    f.out[x,y|:] = compute_equilibrium(1.0, 0.0, 0.0);
}

dynamic StreamCollide {
    real rho = sum(f.in[x,y|:]);
    real ux = compute_velocity_x(f.in[x,y|:], rho);
    real uy = compute_velocity_y(f.in[x,y|:], rho);
    
    f.out[x,y|:] = f.in[x,y|:] 
                 + (1.0/TAU) * (compute_equilibrium(rho, ux, uy) - f.in[x,y|:]);
}

gauge OutputFlow(out = {real rho; real ux; real uy;}) {
    rho = sum(f.in[x,y|:]);
    ux = compute_velocity_x(f.in[x,y|:], rho);
    uy = compute_velocity_y(f.in[x,y|:], rho);
}

node_classes {
    node_class BULK(InitEquilibrium, StreamCollide, OutputFlow);
    node_class LID(InitEquilibrium, StreamCollideLid, OutputFlow);
    node_class WALL(InitEquilibrium, BounceBack, OutputFlow);
}

geometry {
    set_grid_size({Nx, Ny});
    set_grid_periodicity({false, false});
    
    nodes[:,:] = BULK;
    nodes[:,0] = WALL;        // Bottom wall
    nodes[:,Ny-1] = LID;       // Top lid
    nodes[0,:] = WALL;        // Left wall
    nodes[Nx-1,:] = WALL;     // Right wall
}
```

## Language Restrictions

GeLB intentionally restricts certain features to enable automatic parallelization:

### Not Supported
- **No print statements**: Use Gauges for all output
- **No control flow**: No if/while/switch (use intrinsic functions and node classes)
- **No recursion**: Functions must be non-recursive
- **No pointers**: Direct memory manipulation not allowed
- **No user-defined types**: Built-in types only (int, real, bool)

### Supported Alternatives
- **Intrinsic functions**: `sum()`, `dot_prod()` (more coming: min, max, etc.)
- **Node classes**: Different behavior for different spatial regions
- **Pure functions**: Mathematical functions without side effects
- **Compile-time computation**: Constants and ranges resolved at compile time

## Reserved Keywords

The following are reserved and cannot be used as identifiers:
- Coordinates: `x`, `y`, `z`
- Types: `int`, `real`, `bool`
- Blocks: `lattice`, `lattices`, `initializer`, `dynamic`, `gauge`
- Node specification: `node_class`, `node_classes`, `geometry`, `nodes`
- Lattice access: `in`, `out`
- Constants: `const`, `true`, `false`
- Functions: `sum`, `dot_prod`

## Documentation

For comprehensive documentation, visit [gelb-lang.org](https://gelb-lang.org).

Key documentation:
- [Language Tutorial](https://gelb-lang.org/tutorial)
- [Language Reference](https://gelb-lang.org/reference)
- [Developer Guide](https://gelb-lang.org/docs/GeLB_developer_guide/intro-for-devs)
- [API Documentation](https://gelb-lang.org/api)

## Contributing

We welcome contributions! Please see our [Developer Guide](https://gelb-lang.org/docs/GeLB_developer_guide/intro-for-devs) for details on:
- Setting up the development environment
- Understanding the compiler architecture
- Adding new features
- Testing guidelines
- Submitting pull requests

### Development Workflow

1. **Make changes to grammar**: Edit `.g4` files
2. **Regenerate parser**: `./scripts/regenerate_antlr.sh`
3. **Run tests**: `uv run pytest`
4. **Check types**: `uv run mypy gelb`
5. **Format code**: `uv run black gelb`

## Upcoming Features

### Near-term (v0.2)
- Complete Fortran backend implementation
- Additional intrinsic functions (min, max, vector operations)
- Enhanced error messages with source location

### Medium-term (v0.3)
- GPU OpenCL backend
- Multiple gauge output specifications
- Geometry file import
- Conditional node selection in geometry

### Long-term (v1.0)
- Mesh refinement support
- Non-Cartesian meshes
- Distributed memory parallelization (MPI)
- Interactive simulation monitoring

## Using GeLB in Your Work

If you use GeLB for your research, please cite:
```
[Paper citation to be added upon publication]
```

We'd love to hear about your use cases and feature requests!

## License

This project is licensed under the Mozilla Public License 2.0 (MPL-2.0).
See the [LICENSE](https://github.com/dchirila/gelb/blob/main/LICENSE) file for details.

## Authors and Acknowledgments

GeLB was created to make LBM simulations more accessible and productive for researchers. The framework represents years of experience with lattice Boltzmann implementations and lessons learned from the challenges of high-performance computing.

## Contact

- Website: [gelb-lang.org](https://gelb-lang.org)
- GitHub: [github.com/dchirila/gelb](https://github.com/dchirila/gelb)
- Twitter: [@gelb12410715](https://twitter.com/gelb12410715)

---

*"Making lattice Boltzmann simulations as easy to write as they are powerful to run."*