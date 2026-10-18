# Change Log

All notable changes to the "GeLB Language Support" extension will be documented in this file.

## [0.6.3] - 2026-10-19

### Removed
- The snippet and the highlighting for the same-cell opposite-order
  intrinsic, both added in 0.2.0. GeLB 1.0 does not have that
  intrinsic; a wall is `bounce_back_dfs`.

## [0.6.2] - 2026-10-19

### Added
- Syntax highlighting and a `bounceback` snippet for the new
  `bounce_back_dfs` intrinsic (a bounce-back wall in one line).

## [0.6.1] - 2026-10-19

### Changed
- A Problems-panel error or warning underlines the whole name or
  number it points at. gelbc gives a position (a range one character
  wide), so the squiggle used to mark only the first character.

## [0.6.0] - 2026-10-19

### Changed
- **The Run view runs `gelb-run` as a VS Code task the extension
  owns**, instead of typing a command line into a reused "GeLB run"
  terminal. Nothing is typed into any terminal any more, so a half-typed
  command, a program reading its input, or a terminal of the same name
  can no longer swallow or alter a run (each can make a first Run do
  nothing and a second one work). The task runs in the output folder, every time, with
  the arguments as a vector; its output appears in a terminal of the
  panel named "GeLB run: *file* #*n*".
- A `gelb-run` found as a path runs without a shell, with VS Code's
  environment (taken from the login shell when VS Code starts) and
  `terminal.integrated.env.*`; a bare `gelb-run` that only a shell can
  find runs through VS Code's task shell, as
  `cd '<folder>' && 'gelb-run' ...`, and exit status 127 there is
  reported as a setup problem. In a window without a folder, where
  VS Code starts a new task terminal only in the home folder (and
  otherwise launches nothing), the task starts there and changes into
  the output folder itself.
- One run at a time, each with a number: *Run* while a run is starting
  is ignored (the status bar says so); while one is running it asks
  first (*Stop and Run*), whatever the gelb-run setting has become
  since. Nothing is retried on its own.
- *Stop* cancels a run in every stage: before its launch, while its
  task is being created (a task created after Stop is ended at once),
  and while it compiles, simulates or waits for its viewer: Ctrl-C
  (SIGINT) to gelb-run and everything it started, then the task is
  ended if that has not stopped it within 3 seconds. A second *Stop*
  ends the task at once.
- *Open last output in viewer* opens the `.nc` of the last run that
  wrote one; a failed run no longer makes an older file look like its
  result. The row's tooltip gives the file's time.

### Added
- A **Status** row in the Run view: the current or last run (*starting*,
  *running*, *stopping*, *finished*, *stopped*, or why it failed);
  click it for the log.
- The **GeLB Run** output and *GeLB: Show Run Log* (also in the Run
  view's title bar): for every run its number, file, backend, working
  directory, the `gelb-run` used and where it was found, the
  equivalent command line, start, stop and exit status.
- A run that has not reported its start after 10 seconds is reported,
  with buttons to its terminal and the log.
- A GeLB run still going after a window reload is followed again, so
  *Stop* can end it.

### Removed
- The terminal-name search, the `ps` check and the start marker
  (`GELB_RUN_STARTED`) the terminal-based Run needed.

### Development
- `npm test` includes the Run lifecycle (a fake `vscode` module drives
  the Run view through the failure cases this release fixes)
  and its controller; `npm run test:vscode` runs the Run view in a real
  VS Code with a throwaway profile (`xvfb-run` on Linux), and
  `GELB_TEST_REAL=1` adds a run of the real `scripts/gelb-run`.

## [0.5.0] - 2026-09-24

### Added
- **Run view** in the GeLB sidebar, below Program Structure: runs the active `.gelb` file with `gelb-run` in an
  integrated terminal named "GeLB run". Rows for time steps (`-n`),
  write-every (`-w`), constant overrides (`-D`, picked from the
  file's own constants), the seed (`-s`, shown only when the file
  calls `random()`), the backend (`-b`), the viewer toggle
  (`--view`) and the output folder; values are remembered per file.
  Run, Stop (Ctrl-C), Open output folder and Open last output in
  viewer. Run while a run is still going in that terminal, or while
  its line still waits for the shell to start, asks first instead of
  typing a second line into it.
- **GeLB: Run** command, also a ▶ button in the editor title bar and
  a CodeLens (*▶ Run*, *Run with...*) above
  `simulation_description(...)`.
- Settings `gelb.gelbRunCommand`, `gelb.runOutputFolder`,
  `gelb.runDefaultTimeSteps` (1000) and `gelb.runDefaultWriteEvery`
  (100).
- Program Structure shows each constant's type and value
  (`N — int = 65`).

### Fixed
- `gelb.gelbcCommand` and `gelb.gelbViewCommand` honour single and
  double quotes, so a path with spaces works; unquoted values split
  on whitespace as before. Inside double quotes a backslash escapes
  only `"`, `\`, `$` and a backquote, as in sh, so a quoted Windows
  path keeps its backslashes.

### Changed
- The sidebar's Actions view is split in two, to leave the Run view
  its height: **Other Diagnostics** (*Show Source Preview*, *Lint
  Geometry* and a new *Show Problems*, which focuses the Problems
  tab) and **Docs** (the three links, as text links, collapsed at
  first). A new profile gives Program Structure and Run most of the
  sidebar.
- `gelb.gelbcCommand`, `gelb.gelbViewCommand` and
  `gelb.gelbRunCommand` default to empty, and the extension finds
  the tools itself: from the GeLB source checkout the file or
  workspace is in (its `scripts/gelb-run` and `.venv`, or
  `uv run --project`), a GeLB installation, the `PATH` or
  `~/gelb/bin`; `gelb-run` last of all from the terminal's own
  `PATH`. A fresh clone set up with
  `./scripts/gelb_bootstrap.sh` needs no settings; a value in a
  setting still wins.
- Function and gauge snippets now use parameter lists and named
  `-> (...)` results.
- The structural parser recognises function parameters, zero-input
  functions, parameterless gauges, and multiline named-result clauses.
- `->` is highlighted as a single named-result operator.

## [0.4.1]

### Removed
- **`GeLB: Show Source Preview (static)`** command — the static,
  matplotlib-rendered PNG preview. The interactive preview is a
  proper superset (everything the static view showed plus
  hover/click, pan+zoom, 3-D orbit + WASD, stencil animation, and
  per-block inspection), so having both was just cognitive
  overhead. Users who want the matplotlib-rendered PNG can still
  get it on the CLI with `gelb-view source <file>.gelb -o out.png`.
- **`gelb.previewMode` setting** — it only configured the removed
  static preview (geo / algo / both / combined). The interactive
  preview picks up its mode from UI controls within the webview.

### Changed
- **`GeLB: Show Interactive Preview`** renamed to **`GeLB: Show
  Source Preview`** in the command palette. The command ID stays
  `gelb.showInteractivePreview` so any user keybindings survive.
- The editor-title preview button (appears top-right when a
  `.gelb` file is focused) now opens the interactive preview.
- The sidebar's Actions view drops the second preview button;
  the remaining one is labelled "Show Source Preview".

## [0.4.0]

### Added
- **GeLB sidebar in the VSCode activity bar** — new top-level
  container with a lattice-grid icon. Clicking the icon opens a
  panel with two views dedicated to the extension.
- **Program Structure view** — GeLB-aware outline of the currently
  active `.gelb` file, rendered as a tree of top-level blocks
  (`global_constants`, `lattices`, `initializer …`, `dynamic …`,
  `gauge …`, `node_classes`, `geometry`) with nested children
  where meaningful (individual constants, lattice declarations,
  node-class declarations with their block tuple). Click any
  entry to jump to its line in the editor. Updates live on edits
  (debounced).
- **Actions view** — a welcome pane with one-click access to
  *Show Source Preview*, *Show Interactive Preview*, and *Lint
  Geometry*, plus quick links to the reference manual
  (gelb.readthedocs.io), the homepage (gelb-lang.org), and GitHub
  Discussions.
- **DocumentSymbolProvider** — the same parser that powers the
  sidebar now also feeds VSCode's built-in Outline pane, the
  breadcrumb bar, and the *Go to Symbol in Editor* picker
  (`⌘⇧O` / `Ctrl+Shift+O`).
- **WorkspaceSymbolProvider** — *Go to Symbol in Workspace*
  (`⌘T` / `Ctrl+T`) now matches across every `.gelb` file in the
  workspace.
- Extension now also activates on `workspaceContains:**/*.gelb`,
  so the sidebar is available before any `.gelb` file has been
  opened.

## [0.3.0]

### Added
- **Interactive preview** (`GeLB: Show Interactive Preview`) — rendered in a
  webview with live hover / click-to-select. 2D uses a canvas with pan &
  zoom; 3D uses Three.js (`media/three.module.min.js` + `OrbitControls.js`)
  with an orbit camera + WASD fly-through, an orientation gizmo, and
  per-cell raycast selection.
- **Stencil animation** — with a cell selected in the preview, pressing
  **Space** fades in blue squares over every cell a DF is read from, then
  fades them out, then fades in red squares over the cells written to.
  Duration configurable via `gelb.stencilAnimationDurationMs` (default
  3000 ms, range 500–15000).
- **Problems-panel diagnostics** — on open / save of a `.gelb` file the
  extension spawns `gelbc --diagnostics-json` (new compiler flag, frontend
  + midware only, no codegen) and publishes the resulting errors /
  warnings to VSCode's Problems panel. Clicking a row jumps to the
  offending source range. The preview commands refuse to spawn
  `gelb-view` while there are errors, so mid-render tracebacks no longer
  leak to the user.
- **Static source preview** (`GeLB: Show Source Preview`) — a webview
  wrapping `gelb-view source` that shows the geometry heatmap / stencil
  diagram / both.
- **Geometry-lint command** (`GeLB: Lint Geometry`) — runs
  `gelb-view source --lint` and displays the warnings.
- New settings:
  - `gelb.previewMode` (geo / algo / both / combined).
  - `gelb.refreshOnSave` — refresh the preview when the file is saved.
  - `gelb.gelbViewCommand` — path to `gelb-view` (uv users: `"uv run gelb-view"`).
  - `gelb.gelbcCommand` — path to `gelbc` used for Problems-panel
    diagnostics (uv users: `"uv run gelbc"`).
  - `gelb.lintOnOpen` / `gelb.lintOnSave` — toggle automatic diagnostics.
  - `gelb.stencilAnimationDurationMs`.
- Reads / writes side panel renders each access in GeLB source notation
  (`f.in[0, 0, 0 | 0]`, `f.out[...]`) to reduce friction moving between
  preview and code.

## [0.2.0]

### Added
- Syntax highlighting for `function` keyword and user-defined function blocks
- Syntax highlighting for `masked` modifier (masked node classes)
- Syntax highlighting for `array` type and extended numeric types: `int8`, `int16`, `int32`, `int64`, `real16`, `real32`, `real64`
- Syntax highlighting for new intrinsics: `sin`, `cos`, `tan`, `tanh`, `sqrt`, `exp`, `log`, `abs`, `min`, `max`, `mod`, `atan2`, `matmul`, `transpose`, `random`, `upstream_dfs`, and an intrinsic that read a cell's own distribution functions in opposite order (removed in 0.6.3)
- New snippets: `function`, `masked`, `upstream`, `destruct`, and one for that opposite-order intrinsic (removed in 0.6.3)

## [0.1.0]

### Initial Release
- Syntax highlighting for GeLB language constructs
- Support for all GeLB keywords and blocks
- Highlighting for data types (int, real, bool)
- Intrinsic function highlighting (sum, dot_prod)
- Comment support (line and block comments)
- Operator and punctuation highlighting
- Code snippets for common GeLB patterns
- Language configuration for brackets and indentation
- Automatic file association for .gelb files
