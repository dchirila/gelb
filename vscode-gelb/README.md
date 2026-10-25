# GeLB Language Support for Visual Studio Code

This extension provides language support for GeLB (Generic Lattice Boltzmann) files in Visual Studio Code.

## Features

### Syntax Highlighting
Full syntax highlighting for all GeLB language constructs:
- Block keywords: `simulation_description`, `lattices`, `initializer`, `dynamic`, `gauge`, `node_classes`, `geometry`, `function`
- Modifiers and selectors: `const`, `masked`, and lattice-buffer
  selectors `in` / `out`
- Data types: `int`, `int8`, `int16`, `int32`, `int64`, `real`, `real16`, `real32`, `real64`, `bool`, `array`
- Intrinsic functions: `sum`, `dot_prod`, `sin`, `cos`, `tan`, `tanh`, `sqrt`, `exp`, `log`, `abs`, `min`, `max`, `mod`, `atan2`, `matmul`, `transpose`, `random`, `upstream_dfs`, `bounce_back_dfs`
- Coordinate variables: `x`, `y`, `z`
- Comments (line `//` and block `/* */`), operators, and punctuation

### Code Snippets
Productive snippets to speed up GeLB development:
- `gelb-program` — complete GeLB program template
- `lattice` — lattice declaration
- `function` — user-defined function block with named `-> (...)` results
- `initializer` — initializer block
- `dynamic` — dynamic update block
- `gauge` — gauge output block
- `node-class` — node class definition
- `masked` — masked (solid) node class
- `const` — global constant declaration
- `geometry` — geometry setup block
- `upstream` — `upstream_dfs(...)` call
- `bounceback` — `bounce_back_dfs(...)` call
- `destruct` — destructuring assignment `{a, b} = Func(x);`
- `sum` — sum function call
- `dot` — dot product function call
- `lat2d` — 2D lattice selection
- `lat3d` — 3D lattice selection

### Language Configuration
- Automatic bracket matching and closing
- Smart indentation
- Comment toggling (Cmd+/ or Ctrl+/)
- Code folding support

### GeLB sidebar (activity bar)
A dedicated GeLB icon in VSCode's activity bar opens a panel with
four views tailored to `.gelb` development:

- **Program Structure** — a GeLB-aware outline of the currently
  active `.gelb` file. Top-level blocks (`global_constants`,
  `lattices`, each `initializer` / `dynamic` / `gauge`,
  `node_classes`, `geometry`) and nested children (constants,
  lattice declarations, node-class declarations with their
  `(init, dyn, gauge)` tuples). Click an entry to jump to its
  line; the tree updates live as you edit.
- **Run** — runs the file Program Structure shows with `gelb-run`,
  as a VS Code task: its output (compiler messages, the progress
  bar, the MLUPS report) appears in a terminal of the panel named
  "GeLB run: *file* #*n*", and every step of every run in the
  **GeLB Run** output (*Show Run Log*, also in the view's title
  bar). The everyday parameters are rows you click to edit:

  | Row | gelb-run | Default |
  |-----|----------|---------|
  | Time steps | `-n` | `gelb.runDefaultTimeSteps` (1000) |
  | Write every | `-w` | `gelb.runDefaultWriteEvery` (100) |
  | Constants | `-D NAME=VALUE`, one per override, picked from the file's `global_constants` (or typed) | none |
  | Seed (only when the file calls `random()`) | `-s` | from the clock |
  | Backend | `-b` | `cpu_highway` |
  | Open viewer | `--view` | on |
  | Output folder | the run's working directory, where `<name>.nc` lands | next to the source file, or `gelb.runOutputFolder` |

  The values are remembered per file (in the workspace state), so a
  second run with the same overrides is one click. *Run* (also in
  the view's title bar) saves the file and starts `gelb-run` in the
  output folder with these arguments; nothing is typed into a
  terminal. The log shows each run as the equivalent command line,
  for example
  `cd '/Users/me/runs' && '/Users/me/gelb/bin/gelb-run' -n 40000 -w 1000 -D 'N=257' --view '/Users/me/gelb/examples/lbm/2d/lid_driven_cavity_2d_bgk.gelb'`,
  to copy into a terminal for the gelb-run flags the view has no row
  for (`-k`, `-v`, `-F`, `-m stdout`, the `--cuda-*` knobs).

  The **Status** row shows the current or last run, numbered as in
  the log: *starting*, *running* (compiling, simulating, or with its
  viewer window open), *stopping*, *finished*, *stopped*, or why it
  failed; click it for the log. One run at a time: *Run* while a run
  is starting is ignored (the status bar says so); while one is
  running it asks first and offers *Stop and Run*. *Stop* sends
  Ctrl-C to `gelb-run` and everything it started (compiler,
  simulation, viewer) and ends the task when that has not stopped it
  within 3 seconds. A run that has not reported its start after 10
  seconds is reported, with buttons to its terminal and to the log;
  nothing is retried on its own. *Open output folder* and *Open last
  output in viewer* (which starts `gelb-view` on the `.nc` of the
  last run that wrote one; a failed run does not change it) complete
  the view. Constant values containing `'` or `!` are refused, so
  that every run can also be written as a shell line.
- **Other Diagnostics** — buttons for *Show Source Preview*,
  *Lint Geometry* and *Show Problems* (focuses the Problems tab).
- **Docs** — links to the reference manual, the homepage and
  GitHub Discussions; collapsed at first.

The same *Run* is a ▶ button next to the preview button in the
editor title bar, and a CodeLens (*▶ Run* · *Run with...*) above
`simulation_description(...)`; *Run with...* opens the Run view.

### Outline & Go-to-Symbol
The same structural parser feeds VSCode's built-in Outline pane,
the breadcrumb bar at the top of the editor, the *Go to Symbol in
Editor* picker (`⌘⇧O` / `Ctrl+Shift+O`), and *Go to Symbol in
Workspace* (`⌘T` / `Ctrl+T`) — the last of which searches across
every `.gelb` file in the workspace.

### Commands (via `Cmd+Shift+P` / `Ctrl+Shift+P`)
- **GeLB: Show Source Preview** — live geometry + stencil explorer.
  2D: pan (Alt-drag), zoom (wheel), click cells to inspect. 3D: orbit
  (drag), dolly (wheel), fly-through (WASD + Q/E), click cubes to select,
  orientation gizmo bottom-left. Press **Space** on a selected cell to
  play the blue-reads / red-writes stencil animation.
- **GeLB: Lint Geometry** — run geometry-lint warnings and open the GeLB
  output channel.
- **GeLB: Run** — run the active `.gelb` file with `gelb-run`, using
  the parameters of the sidebar's Run view (see above). **GeLB: Stop
  Run** stops it; **GeLB: Show Run Log** opens the GeLB Run output.

### Problems-panel diagnostics
On open / save of a `.gelb` file the extension runs
`gelbc --diagnostics-json` (frontend + midware only, no codegen) and
publishes the resulting errors / warnings to VSCode's Problems panel with
clickable source ranges. While there are any errors, the preview
commands refuse to run and show a one-line toast pointing at the panel.

### Settings
The three command settings (`gelbcCommand`, `gelbViewCommand`,
`gelbRunCommand`) are empty by default, and the extension finds the
tools itself, looking from the `.gelb` file's folder and the
workspace folders upwards:

1. a GeLB source checkout (as cloned and set up with
   `./scripts/gelb_bootstrap.sh`): its `scripts/gelb-run`, and
   `gelbc` / `gelb-view` from its `.venv` (through
   `uv run --project <checkout>` when there is no `.venv` yet);
2. a GeLB installation, such as the macOS installer's `~/gelb`: its
   `bin/` commands;
3. otherwise `gelbc`, `gelb-view`, `gelb-run` on the `PATH`, then
   `~/gelb/bin`;
4. for `gelb-run` only, finally the bare name, which the Run view
   then runs through VS Code's task shell (`cd '<folder>' &&
   'gelb-run' ...`), whose `PATH` can be longer than VS Code's own
   (`terminal.integrated.env.*`, what the shell reads when it
   starts). A `gelb-run` found as a path runs without a shell, with
   VS Code's environment (taken from your login shell when VS Code
   starts) plus `terminal.integrated.env.*`.

When `gelbc` or `gelb-view` is not found, the command says so and
offers to open the setting; when the task shell cannot find
`gelb-run` either (exit status 127), the Run view says so too. A
value in a setting always wins. The settings
accept a path with spaces: quote it with `'...'`
or `"..."` in the first two (they may carry arguments, such as
`uv run gelbc`), and write it plainly in `gelbRunCommand` (a single
executable). Inside double quotes a backslash escapes only `"`, `\`,
`$` and a backquote, so `"C:\Program Files\GeLB\gelbc.exe"` keeps
its backslashes.

| Setting | Default | Purpose |
|---------|---------|---------|
| `gelb.gelbcCommand` | `""` (found) | Command that runs `gelbc` for Problems-panel diagnostics, e.g. `"uv run gelbc"`. |
| `gelb.gelbViewCommand` | `""` (found) | Command that runs `gelb-view` for the previews, Lint Geometry and the Run view's viewer. |
| `gelb.gelbRunCommand` | `""` (found) | Name or path of `gelb-run` for the Run view: one executable, no arguments; a relative path such as `./scripts/gelb-run` is taken from the workspace folder. The macOS installer writes `~/gelb/bin/gelb-run`. |
| `gelb.runOutputFolder` | `""` | Folder the Run view runs in (where the `.nc` lands); empty means next to the source file. Relative to the workspace folder; `~` and `${workspaceFolder}` expanded; created if missing. Per workspace folder. |
| `gelb.runDefaultTimeSteps` | `1000` | Time steps a file starts with in the Run view. |
| `gelb.runDefaultWriteEvery` | `100` | Output interval a file starts with in the Run view. |
| `gelb.lintOnOpen` | `true` | Run diagnostics when a `.gelb` file is opened. |
| `gelb.lintOnSave` | `true` | Re-run diagnostics when a `.gelb` file is saved. |
| `gelb.refreshOnSave` | `true` | Re-render the active preview on save. |
| `gelb.stencilAnimationDurationMs` | `3000` | Total duration of the Space-triggered stencil animation in the source preview, split into four equal phases (reads-in / out, writes-in / out). |

## Installation

### From a source checkout

From the repository root, with Node.js and npm installed:

```bash
./scripts/install-vscode-ext.sh
```

The script builds the extension and copies what VS Code needs (without
`node_modules`, `src/` and `test/`) into `~/.vscode/extensions` on macOS
and Linux; `--extensions-dir DIR` targets another folder, `--check`
compares the installed and the source versions. Reload VS Code afterwards
(*Developer: Reload Window* in the Command Palette). On Windows, run
`npm ci && npm run compile` in `vscode-gelb/` and copy the folder, without
`node_modules`, into `%USERPROFILE%\.vscode\extensions\`.

### From a VSIX package

With Node.js 22 or newer (the packager needs it):

```bash
cd vscode-gelb && npm ci && npm run compile
npx @vscode/vsce package --no-dependencies
```

writes `gelb-lang-<version>.vsix`. In VS Code, open the Extensions view
(`Ctrl+Shift+X` / `Cmd+Shift+X`), choose *Install from VSIX...* from its
`...` menu and pick the file. The macOS bundle installs the extension this
way.

### Development mode

Run `npm ci` in `vscode-gelb/`, open that folder in VS Code and press F5:
an Extension Development Host window starts with the extension loaded.

## Usage

The extension activates automatically when a `.gelb` file is opened.

Type a snippet prefix and press Tab to expand:
- `function` → user-defined function block with named results
- `upstream` → `upstream_dfs(f, x, y, {EX, EY})`
- `masked` → `node_class SOLID() masked;`
- `destruct` → `{rho, ux, uy} = Macro(fIn);`
- And all the other snippets listed above.

## Testing

```bash
cd vscode-gelb
npm install
npm test
```

## License

This extension is licensed under the Mozilla Public License 2.0 (MPL-2.0).
