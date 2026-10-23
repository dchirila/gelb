# GeLB 1.0.0 on your Mac: start here

This folder is a complete GeLB installation for macOS on Apple Silicon:
the compiler (`gelbc`), the compile-and-run wrapper (`gelb-run`), the
viewer (`gelb-view`), all 86 examples, the user tutorial, the VS Code
extension, and a private Python with every package they need, plus the
OpenMP, HDF5 and NetCDF libraries. Nothing is downloaded and nothing is
installed system-wide. The one thing it uses from your Mac is the C++
compiler that comes with Xcode (or with the Command Line Tools).

`VERSION` says exactly what was built, from which commit, and when.

## 1. Install

Packaged installers for macOS and Ubuntu follow in release 1.0.1;
release 1.0 is installed from a source checkout (`git clone`, then
`scripts/gelb_bootstrap.sh`, which puts the same three commands on your
PATH), and the rest of this page describes the package.

Double-click `GeLB-1.0.0.pkg` and follow the installer. It needs no
administrator password: everything goes into `~/gelb`. If macOS says
the package is from an unidentified developer, right-click (or
Control-click) it, choose *Open*, and confirm; the package is not
signed with a paid Apple developer certificate.

On the **Installation Type** page tick the shells that should find the
GeLB commands (zsh, bash, tcsh; your login shell is preselected) and
whether to install the VS Code extension. The installer

- copies GeLB to `~/gelb` (an existing `~/gelb` is moved to
  `~/gelb.bak-<date>` first, and the installation stops if that fails);
- appends one PATH line to each ticked shell's startup file:
  `~/.zprofile`, `~/.bash_profile` (or `~/.profile` if that is what you
  use) or `~/.tcshrc` (or `~/.cshrc`); running it again never adds the
  line twice;
- writes `~/gelb/.vscode/settings.json` and, if ticked, installs the
  VS Code extension;
- compiles and runs one example as a check (20 to 40 s) and writes
  `~/gelb/INSTALL_REPORT.txt`. If the check fails, that report opens by
  itself and says what to do.

From Terminal instead (configures your login shell):

    installer -pkg GeLB-1.0.0.pkg -target CurrentUserHomeDirectory

`installer -pkg ... -showChoicesXML` lists the choices and
`-applyChoiceChangesXML file.xml` changes them.

## 2. Open a new terminal

The PATH line takes effect in new terminal windows. Then

    gelb-run -n 1000 -w 100 --view ~/gelb/examples/lbm/2d/taylor_green_vortex_2d_bgk.gelb

translates the example to C++, compiles it (20 to 40 s the first time;
the compiler is doing real work), runs 1000 time steps writing every
100th, leaves `taylor_green_vortex_2d_bgk.nc` in the current directory,
and opens the viewer on it. `gelb-run --help` lists every option; the
ones you will use are `-n` (time steps), `-w` (write every N steps),
`-D NAME=VALUE` (override a constant) and `--view`.

## 3. Look at results

    gelb-view taylor_green_vortex_2d_bgk.nc            # interactive GUI
    gelb-view taylor_green_vortex_2d_bgk.nc --no-gui   # static plots

Or add `--view` (`-V`) to `gelb-run` to open the viewer right after the
run. In the GUI, pick variables in the tree on the left; the composite
plots (vector field, streamlines, vorticity, particle animation) are
under the multi-variable entries.

    gelb-view ~/gelb/examples/lbm/2d/lid_driven_cavity_2d_bgk.gelb

shows the *geometry and stencils* of a program without running it
(`gelb-view source FILE.gelb -o geo.png` saves the same picture
headless, and `--text` prints the geometry as an ASCII grid).

## 4. VS Code extension

The installer adds it when the `code` command exists. Otherwise, in VS
Code: Extensions view, the `...` menu, *Install from VSIX...*, and pick
the `gelb-lang-*.vsix` in `~/gelb/vscode-gelb/`. (To get the `code` command,
run *Shell Command: Install 'code' command in PATH* from VS Code's
Command Palette.)

Then open the **`~/gelb` folder** in VS Code (File, Open Folder). The
folder carries the three settings the extension needs
(`.vscode/settings.json`). You get syntax highlighting, snippets, an
outline of the program's blocks, errors in the Problems panel each
time you save, and a geometry/stencil preview for the file you are
editing. The sidebar's **Run** view (the GeLB icon on the left) runs
that file with `gelb-run`, its output in VS Code's terminal panel: set
the time steps, override a constant such as `N`, press the play
button, and the viewer opens when the run ends.

## 5. Things to try

All commands run from any folder; the output `.nc` file lands in the
current directory. Add `--view` to open the viewer when the run ends.
Timings are rough figures for an Apple-Silicon laptop.

1. **Karman vortex street**: channel flow past a cylinder, 1024x128,
   about a minute:

       gelb-run -n 20000 -w 500 --view ~/gelb/examples/lbm/2d/channel_flow_circle_obstacle_2d_bgk.gelb

   Look at `uy` or the vorticity composite plot.

2. **Rayleigh-Benard convection**: hot plate below, cold above, six
   rolls appear, under a minute:

       gelb-run -n 400000 -w 20000 --view ~/gelb/examples/lbm/2d/rayleigh_benard_2d_mrt.gelb

   Look at `T`. Then change the physics from the command line:
   `-D RA=1500.0` is below the critical Rayleigh number (about 1708) and
   nothing moves; `-D RA=30000.0` convects three hundred times harder.

3. **Conway's Game of Life**: not a fluid at all; GeLB does cellular
   automata too, seconds:

       gelb-run -n 400 -w 4 --view ~/gelb/examples/lgca/2d/game_of_life_random_ICs.gelb
       gelb-run -n 400 -w 4 --view ~/gelb/examples/lgca/2d/game_of_life_glider.gelb

   Use the time slider in the viewer.

4. **Lid-driven cavity**, the textbook benchmark, at a resolution the
   plots deserve, about a minute:

       gelb-run -n 40000 -w 1000 -D N=257 --view ~/gelb/examples/lbm/2d/lid_driven_cavity_2d_bgk.gelb

   Streamlines show the main vortex and the corner eddies. Try
   `-D U_LID=0.2` for a higher Reynolds number.

5. **Wind-driven ocean basin**: Salmon's double-gyre shallow-water
   model, one active layer over a still abyss, seconds:

       gelb-run -n 20000 -w 200 --view ~/gelb/examples/lbm/2d/reduced_gravity_2d_sw_d2q9.gelb

6. **3D Taylor-Green vortex**: the viewer slices 3D fields, half a
   minute:

       gelb-run -n 2000 -w 100 --view ~/gelb/examples/lbm/3d/taylor_green_vortex_3d_bgk.gelb

7. **Flow past Madeira**: the real coastline (ETOPO 2022) as an
   obstacle, on a 768x1536 grid. This is the long one (10 to 20 minutes
   depending on the Mac), and the output file is a few hundred MB, so
   keep `-w` large:

       gelb-run -n 100000 -w 20000 --view ~/gelb/examples/softwarex-2026-paper/flow_past_madeira_2d_bgk_zouhe.gelb

   The vortex street trails SSW as in the satellite images.

8. **Break something on purpose.** Open any example in VS Code, misspell
   a variable or drop a `;`, and watch the Problems panel. Then change a
   constant (`TAU`, `U_LID`, the grid size) and re-run: every `const` in
   `global_constants` can be overridden with `-D NAME=VALUE` without
   editing the file.

Every example starts with a comment block explaining the physics and the
boundary conditions; `examples/sukop/` follows the worked examples
of Sukop & Thorne (2006).

## 6. Manual

`~/gelb/docs/html/index.html`: the user tutorial (start with "GeLB in
10 minutes").

## 7. If something goes wrong

- *`clang++: command not found`, or a dialog about developer tools*:
  install Xcode or the Command Line Tools (`xcode-select --install`).
  If Xcode is installed but has never been opened, its license is
  pending: `sudo xcodebuild -license accept`.
- *C++ errors mentioning `omp.h` or `netcdf.h`*: the bundle's own
  headers are not being found. `which gelb-run` must answer
  `~/gelb/bin/gelb-run`; if it names another copy, fix the PATH line.
- *The viewer window does not open*: `gelb-view FILE.nc --no-gui`
  always works, and `-o plots.png` saves the plots instead of showing
  them.
- *Threads*: `gelb-run` uses the performance cores only (4 on an M1 or
  M4 MacBook Air); set `OMP_NUM_THREADS` to change that. The
  `gpu_cuda_cpp` backend needs an NVIDIA GPU and does not apply to Macs;
  `cpu_fortran_serial` needs gfortran, which the bundle does not carry.
- *A program of your own does not compile*: `gelbc FILE.gelb
  --diagnostics-json` prints every error with its line and column; the
  VS Code extension shows the same in the Problems panel.
- *Uninstall*: delete `~/gelb` and the two GeLB lines the installer
  added to your shell startup file (`~/.zprofile`, `~/.bash_profile`,
  `~/.profile`, `~/.tcshrc` or `~/.cshrc`); remove the extension from
  VS Code's Extensions view. The installer's receipts sit in
  `~/Library/Receipts` as `org.gelb.pkg.*` and can be deleted too.
