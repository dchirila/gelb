# SoftwareX 2026 paper examples

Pinned copies of every GeLB program referenced in the SoftwareX paper
*"GeLB: A Domain-Specific Language and Compiler for Lattice Boltzmann
Simulations"* (Chirila & Lohmann, 2026), plus the two programs written
specifically for the paper's Section 3 ("Illustrative examples").
The copies freeze what the paper describes; the canonical, maintained
versions of the Section 3.1 programs and of
`rayleigh_benard_2d_mrt.gelb` live in `examples/lbm/2d/`.

All commands below are run from the repo root.

## Section 3.1 — Taylor–Green vortex (accuracy + performance)

| File | Used for |
|------|----------|
| `taylor_green_vortex_2d_bgk.gelb` | convergence figure (BGK rows), performance table rows, appendix listing |
| `taylor_green_vortex_2d_mrt.gelb` | convergence figure (MRT rows) |
| `poiseuille_flow_2d_mrt.gelb` | convergence figure (Poiseuille rows) |
| `lid_driven_cavity_2d_bgk.gelb` | performance table rows |

```sh
# convergence data (writes the L2-error table the figure is drawn from):
uv run python scripts/validate_analytical.py \
    --cases taylor_green_bgk taylor_green_mrt poiseuille \
    --resolutions 16 32 64 128 256
```

Note: the harness script above resolves the canonical paths under
`examples/lbm/2d/`; the copies here are archival pins (pinned 2026-08-16,
identical up to ASCII-normalized punctuation in comments).

The `terse/` subfolder holds print-compact twins of the programs the
paper actually typesets (comments/whitespace condensed, code
token-identical — see `terse/README.md`); the paper's printed listings
are byte-identical to those.

## Section 3.2 — Rayleigh–Bénard convection

| File | Used for |
|------|----------|
| `rayleigh_benard_2d_bgk.gelb` | Listing 1 (collision dynamic) + appendix listing; seeded with the same delta-plus-noise initial condition as the MRT program, so it convects at the same Ra |
| `rayleigh_benard_2d_mrt.gelb` | temperature-snapshot figure, `find_ra_critical.py` |

```sh
# snapshot figure data (Ra = 1e4, six convection cells):
./scripts/gelb-run -b cpu_highway -n 400000 -w 100000 \
    examples/softwarex-2026-paper/rayleigh_benard_2d_mrt.gelb
# critical-Rayleigh bracketing:
uv run python scripts/find_ra_critical.py --backend cpu
```

## Section 3.3 — Kármán vortex streets: cylinder + Madeira

Both programs share the same numerics and boundary treatment: D2Q9 BGK,
Zou–He velocity inlet along the top row, zero-gradient outflow along
the bottom row, periodic east–west boundaries, half-way bounce-back on
the obstacle ring. Flow runs top → bottom in both, so the island keeps its
normal map orientation (north up) and the street trails SSW as in the
satellite images. See the header comments in each program for the
physics rationale (atmospheric vs. oceanic wake, Reynolds numbers).

| File | Used for |
|------|----------|
| `flow_past_cylinder_2d_bgk_zouhe.gelb` | figure panel (a) — validation anchor, Re = 150 |
| `flow_past_madeira_2d_bgk_zouhe.gelb` | figure panel (b) — real coastline, Re = 300 |
| `gen_flow_past_madeira.py` | regenerates the Madeira program from ETOPO 2022 bathymetry |

```sh
./scripts/gelb-run -b cpu_highway -n 200000 -w 10000 \
    examples/softwarex-2026-paper/flow_past_cylinder_2d_bgk_zouhe.gelb
./scripts/gelb-run -b cpu_highway -n 250000 -w 10000 \
    examples/softwarex-2026-paper/flow_past_madeira_2d_bgk_zouhe.gelb
```

The Madeira program is committed as generated; rerun the generator only
to change parameters. It needs `madeira_etopo2022.tif` (~4 MB, not
committed), downloadable via:

```sh
curl "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_all/ImageServer/exportImage?bbox=-17.60,32.30,-16.50,33.20&bboxSR=4326&size=1056,864&format=tiff&pixelType=F32&noData=&interpolation=RSP_BilinearInterpolation&f=image" \
     -o madeira_etopo2022.tif
```

## Figures

The matplotlib scripts that turn these runs into the paper's figures
live in the paper repository under `figs-prep/figs/` (each directory is
self-contained: generator script + input data + `REPRODUCE` notes).
