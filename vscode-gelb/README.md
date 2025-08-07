# GeLB Language Support for Visual Studio Code

This extension provides rich language support for GeLB (Generic Lattice Boltzmann) files in Visual Studio Code.

## Features

### Syntax Highlighting
Full syntax highlighting support for GeLB language constructs:
- Keywords (`simulation_description`, `lattices`, `initializer`, `dynamic`, `gauge`, etc.)
- Data types (`int`, `real`, `bool`)
- Constants and literals
- Intrinsic functions (`sum`, `dot_prod`)
- Comments (line and block)
- Operators and punctuation
- Coordinate variables (`x`, `y`, `z`)

### Code Snippets
Productive code snippets to speed up GeLB development:
- `gelb-program` - Complete GeLB program template
- `lattice` - Lattice declaration
- `initializer` - Initializer block
- `dynamic` - Dynamic update block
- `gauge` - Gauge output block
- `node-class` - Node class definition
- `const` - Global constant declaration
- `geometry` - Geometry setup
- `sum` - Sum function call
- `dot` - Dot product function call
- `lat2d` - 2D lattice selection
- `lat3d` - 3D lattice selection

### Language Configuration
- Automatic bracket matching and closing
- Smart indentation
- Comment toggling (Cmd+/ or Ctrl+/)
- Code folding support

## Installation

### From VSIX Package
1. Download the `.vsix` file from the releases
2. Open VS Code
3. Go to Extensions view (Cmd+Shift+X or Ctrl+Shift+X)
4. Click on the "..." menu and select "Install from VSIX..."
5. Select the downloaded `.vsix` file

### From Source
1. Clone the repository
2. Navigate to `vscode-gelb/` directory
3. Run `npm install` to install dependencies
4. Open the folder in VS Code
5. Press F5 to launch a new VS Code window with the extension loaded

## Usage

The extension automatically activates when you open a `.gelb` file. Features include:

### Creating a New GeLB File
1. Create a new file with `.gelb` extension
2. Type `gelb-program` and press Tab to insert a complete program template
3. Use Tab to navigate through the template placeholders

### Using Snippets
Type the snippet prefix and press Tab:
- `lattice` → Lattice declaration
- `const` → Constant declaration
- `dynamic` → Dynamic block
- And more...

### Example GeLB Program

```gelb
simulation_description("2D Flow Simulation");

global_constants {
    const int Nx = 128;
    const int Ny = 128;
    const real TAU = 0.6;
}

lattices {
    lattice f(d=2, q=9, df_type=real);
}

initializer Init {
    f.out[x,y|:] = 0.0;
}

dynamic Update {
    real rho = sum(f.in[x,y|:]);
    f.out[x,y|:] = f.in[x,y|:] + (1.0/TAU) * delta;
}

gauge Output(out = {real density;}) {
    density = sum(f.in[x,y|:]);
}

node_classes {
    node_class BULK(Init, Update, Output);
}

geometry {
    set_grid_size({Nx, Ny});
    set_grid_periodicity({true, true});
    nodes[:,:] = BULK;
}
```

## Language Reference

### Keywords
- Structure: `simulation_description`, `global_constants`, `lattices`, `node_classes`, `geometry`
- Blocks: `lattice`, `initializer`, `dynamic`, `gauge`, `node_class`
- Geometry: `set_grid_size`, `set_grid_periodicity`, `nodes`
- Modifiers: `const`, `in`, `out`

### Data Types
- `int` - Integer type
- `real` - Floating-point type
- `bool` - Boolean type

### Built-in Functions
- `sum(array)` - Sum all elements of an array
- `dot_prod(array1, array2)` - Compute dot product

### Special Variables
- `x`, `y`, `z` - Coordinate variables (automatically available in context)

## Testing

To run the grammar tests:
```bash
cd vscode-gelb
npm install
npm test
```

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests to improve the extension.

## License

This extension is licensed under the Mozilla Public License 2.0 (MPL-2.0).

## More Information

- [GeLB Language Documentation](https://gelb-lang.org)
- [GeLB GitHub Repository](https://github.com/dchirila/gelb)
- [Report Issues](https://github.com/dchirila/gelb/issues)