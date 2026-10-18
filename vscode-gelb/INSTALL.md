# Installation Instructions for GeLB VSCode Extension

## Features

- **Syntax highlighting** for `.gelb` files
- **Snippets** for common GeLB constructs
- **Live preview pane** showing geometry / stencils / combined view
  while you edit (command: "GeLB: Show Source Preview")
- **Geometry lint warnings** (command: "GeLB: Lint Geometry")

The preview features require the `gelb-view` CLI to be installed
(see the main GeLB project README).  By default the extension
expects `gelb-view` on PATH; if you use `uv`, set the
`gelb.gelbViewCommand` setting to `uv run gelb-view`.

## Quick Install (For Users)

### Method 1: Install in VSCode directly
1. Build the extension first (one-time, see "Development Setup" below)
2. Copy the `vscode-gelb` folder to your VSCode extensions directory:
   - **Windows**: `%USERPROFILE%\.vscode\extensions\`
   - **macOS**: `~/.vscode/extensions/`
   - **Linux**: `~/.vscode/extensions/`

3. Restart VSCode

4. Open any `.gelb` file to see syntax highlighting and run
   "GeLB: Show Source Preview" from the command palette

### Method 2: Install from VSIX (if packaged)
1. Open VSCode
2. Press `Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows/Linux)
3. Type "Install from VSIX" and select the command
4. Browse to and select the generated `.vsix` file
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

4. Compile TypeScript:
   ```bash
   npm run compile        # one-shot build
   # OR
   npm run watch          # rebuild on save during development
   ```

5. Open in VSCode:
   ```bash
   code .
   ```

### Testing the Extension
1. Press `F5` in VSCode to launch a new Extension Development Host window
2. Open a `.gelb` file in the new window
3. Verify syntax highlighting works
4. From the command palette (`Cmd+Shift+P` / `Ctrl+Shift+P`),
   run "GeLB: Show Source Preview" — a webview should appear with
   the rendered geometry.  Edit the file and save; the preview
   refreshes automatically.

### Running Tests
```bash
# Run grammar structure tests
node test/grammar.test.js

# Run full test suite (requires dependencies): grammar, parser, the
# Run view's command line and its request lifecycle; no VS Code needed
npm test

# The Run view in a real VS Code (an Extension Development Host with a
# throwaway profile and only this extension), against a stand-in
# gelb-run. Linux, off-screen:
env -u WAYLAND_DISPLAY xvfb-run -a -s "-screen 0 1600x1000x24" npm run test:vscode
# macOS:
npm run test:vscode
# plus a run of the real scripts/gelb-run (compiles an example):
GELB_TEST_REAL=1 npm run test:vscode
```

VS Code is `/usr/share/code/code` when it exists (or `GELB_VSCODE`),
otherwise `@vscode/test-electron` downloads one.

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