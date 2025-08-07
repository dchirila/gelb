# Installation Instructions for GeLB VSCode Extension

## Quick Install (For Users)

### Method 1: Install in VSCode directly
1. Copy the `vscode-gelb` folder to your VSCode extensions directory:
   - **Windows**: `%USERPROFILE%\.vscode\extensions\`
   - **macOS**: `~/.vscode/extensions/`
   - **Linux**: `~/.vscode/extensions/`

2. Restart VSCode

3. Open any `.gelb` file to see syntax highlighting in action

### Method 2: Install from VSIX (if packaged)
1. Open VSCode
2. Press `Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows/Linux)
3. Type "Install from VSIX" and select the command
4. Browse to and select the `gelb-lang-0.1.0.vsix` file
5. Restart VSCode

## Development Setup

### Prerequisites
- Node.js (v14 or higher)
- npm or yarn
- VSCode

### Setup Steps
1. Clone the repository
2. Navigate to the extension directory:
   ```bash
   cd vscode-gelb
   ```

3. Install dependencies:
   ```bash
   npm install
   ```

4. Open in VSCode:
   ```bash
   code .
   ```

### Testing the Extension
1. Press `F5` in VSCode to launch a new Extension Development Host window
2. Open a `.gelb` file in the new window
3. Verify syntax highlighting works

### Running Tests
```bash
# Run grammar structure tests
node test/grammar.test.js

# Run full test suite (requires dependencies)
npm test
```

## Packaging the Extension

### Install vsce (Visual Studio Code Extension manager)
```bash
npm install -g vsce
```

### Package the extension
```bash
cd vscode-gelb
vsce package
```

This creates a `.vsix` file that can be distributed and installed.

## Publishing to VSCode Marketplace

### Prerequisites
1. Create a publisher account at https://marketplace.visualstudio.com
2. Get a Personal Access Token from Azure DevOps

### Publish
```bash
vsce publish
```

## Troubleshooting

### Extension not activating
- Check that files have `.gelb` extension
- Verify extension is enabled in Extensions view
- Check VSCode developer console for errors (`Cmd+Shift+P` > "Developer: Toggle Developer Tools")

### Syntax highlighting not working
- Ensure the file is saved with `.gelb` extension
- Try reloading the window (`Cmd+R` or `Ctrl+R`)
- Check that no other extensions are conflicting

### Testing issues
- Make sure all npm dependencies are installed
- For the full test suite, you may need to install additional dependencies:
  ```bash
  npm install --save-dev vscode-textmate vscode-oniguruma
  ```

## File Locations

After installation, the extension files are located at:
- **Grammar**: `syntaxes/gelb.tmLanguage.json`
- **Language Config**: `language-configuration.json`
- **Snippets**: `snippets/gelb.json`
- **Package Info**: `package.json`