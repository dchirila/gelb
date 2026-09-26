#!/usr/bin/env python3
"""Generate flow_past_madeira_2d_bgk_zouhe.gelb (SoftwareX paper, Sec. 3.3).

Rasterizes the real Madeira coastline (ETOPO 2022 bathymetry cutout) into
run-length `nodes[x1:x2, y] = LAND;` geometry statements, embedded in a
D2Q9 BGK program with open boundaries: a Zou-He velocity inlet along the
top (northern) row, a zero-gradient outflow along the bottom (southern)
row, periodic east-west boundaries.  The island keeps its normal map
orientation (north up); the inflow comes from the NNE at 22.5 deg off
north, the prevailing trade-wind direction during the observed Madeira
vortex-street events, so the street trails to the SSW exactly as in the
satellite imagery.

Atmosphere or ocean?  The iconic Madeira vortex streets are ATMOSPHERIC:
trade winds (~5-10 m/s from the NE quadrant) flow around the island,
whose terrain (Pico Ruivo, 1862 m) pierces the trade inversion
(~800-1500 m), so the cloud-topped boundary layer behaves like a
quasi-2D fluid flowing around an obstacle.  The oceanic flow past
Madeira (Canary Current, ~0.05-0.2 m/s toward the SW) also sheds island
eddies, but the regular Karman street seen from space lives in the
cloud deck.  This 2D single-layer simulation is therefore closest to
the atmospheric case, with two caveats baked into the header of the
generated program: the sea-level coastline stands in for the (smaller)
terrain contour at inversion height, and the Reynolds number is a
laboratory-scale stand-in (Re = 300) for the effective large-eddy Re of
the real flow.

Bathymetry input: madeira_etopo2022.tif, searched for next to this
script, in the CWD, and in the paper repo's figs-prep directory.
To (re-)download (~4 MB, ETOPO 2022 via NOAA NCEI):

    curl "https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_all/ImageServer/exportImage?bbox=-17.60,32.30,-16.50,33.20&bboxSR=4326&size=1056,864&format=tiff&pixelType=F32&noData=&interpolation=RSP_BilinearInterpolation&f=image" \
         -o madeira_etopo2022.tif

Pipeline:

    python3 gen_flow_past_madeira.py   # -> flow_past_madeira_2d_bgk_zouhe.gelb
    cd <gelb-repo>
    ./scripts/gelb-run -b cpu_highway -n 250000 -w 10000 \
        examples/softwarex-2026-paper/flow_past_madeira_2d_bgk_zouhe.gelb
"""

import math
import os

import numpy as np
from PIL import Image

# ---------------- lattice / physics parameters ----------------
NX, NY = 768, 1536        # east-west (periodic) x north-south (inlet/outlet)
ISLAND_LEN = 80           # island east-west (long-axis) extent, lattice cells
CX_FRAC, CY_FRAC = 0.65, 0.72   # island center (east of middle, upper third:
                                # the SSW-trailing wake stays inside the frame)
TAU = 0.54                # nu = (TAU - 0.5)/3 = 1/75
U_IN = 0.05               # inflow speed; Ma = U*sqrt(3) ~ 0.087
AZ_DEG = 22.5             # inflow azimuth off north (NNE trade wind)

NU = (TAU - 0.5) / 3.0
U_INX = -U_IN * math.sin(math.radians(AZ_DEG))   # westward component
U_INY = -U_IN * math.cos(math.radians(AZ_DEG))   # southward component

# ---------------- locate the bathymetry cutout ----------------
_here = os.path.dirname(os.path.abspath(__file__))
_candidates = [
    os.path.join(_here, "madeira_etopo2022.tif"),
    "madeira_etopo2022.tif",
    os.path.expanduser(
        "~/Research/gelb/paper/figs-prep/figs/island_wake/madeira_etopo2022.tif"),
]
TIF = next((p for p in _candidates if os.path.exists(p)), None)
if TIF is None:
    raise SystemExit("madeira_etopo2022.tif not found -- see the download "
                     "command in this script's docstring")

# ---------------- extract the Madeira land mask ----------------
# The GeoTIFF covers lon [-17.60, -16.50] x lat [32.30, 33.20] at 1056x864;
# row 0 = northern edge.  Crop to Madeira proper (excludes Porto Santo and
# the Desertas), then correct for the cos(lat) longitude stretch.
elev = np.array(Image.open(TIF), dtype=np.float32)

LON0, LON1, LAT0, LAT1 = -17.60, -16.50, 32.30, 33.20
W, Hpx = elev.shape[1], elev.shape[0]

def px_x(lon): return int((lon - LON0) / (LON1 - LON0) * W)
def px_y(lat): return int((LAT1 - lat) / (LAT1 - LAT0) * Hpx)

crop = elev[px_y(32.92):px_y(32.58), px_x(-17.32):px_x(-16.62)]
land = crop > 0.0

# cos(lat) correction: shrink the x-axis so distances are isotropic
coslat = np.cos(np.deg2rad(32.75))
ys, xs = np.nonzero(land)
x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
land = land[y0:y1, x0:x1]

# scale so the island's E-W extent is ISLAND_LEN lattice cells
scale_x = ISLAND_LEN / land.shape[1]
scale_y = scale_x / coslat          # N-S pixels cover more ground per px
out_w = ISLAND_LEN
out_h = max(1, int(round(land.shape[0] * scale_y)))

# area-average downsampling + 0.5 threshold (no scipy dependency)
src_y = (np.arange(out_h) / scale_y).astype(int).clip(0, land.shape[0] - 1)
src_x = (np.arange(out_w) / scale_x).astype(int).clip(0, land.shape[1] - 1)
step_y = max(1, int(1.0 / scale_y))
step_x = max(1, int(1.0 / scale_x))
mask = np.zeros((out_h, out_w), dtype=bool)
for j in range(out_h):
    for i in range(out_w):
        block = land[src_y[j]:src_y[j] + step_y, src_x[i]:src_x[i] + step_x]
        mask[j, i] = block.mean() >= 0.5

# GeLB convention: y grows upward; image row 0 is north -> flip.
# NO rotation: the island keeps its map orientation (north up); the
# tilted inlet velocity supplies the correct incidence instead.
mask = mask[::-1, :]

# ---------------- run-length encode into geometry spans ----------------
cx0 = int(NX * CX_FRAC) - out_w // 2
cy0 = int(NY * CY_FRAC) - out_h // 2
spans = []
for j in range(out_h):
    row = np.nonzero(mask[j])[0]
    if row.size == 0:
        continue
    start = prev = row[0]
    for i in list(row[1:]) + [None]:
        if i is None or i != prev + 1:
            spans.append((cx0 + start, cx0 + prev + 1, cy0 + j))
            start = i
        prev = i if i is not None else prev

drift = (cy0) * math.tan(math.radians(AZ_DEG))
print(f"island: {out_w}x{out_h} cells (E-W x N-S), {mask.sum()} land cells, "
      f"{len(spans)} span statements")
print(f"center ({cx0 + out_w // 2}, {cy0 + out_h // 2}); "
      f"Re = {U_IN * out_w / NU:.0f} (D = {out_w} cells E-W); "
      f"wake drifts ~{drift:.0f} cells west by the outlet "
      f"(island cx {cx0 + out_w // 2} -> stays in [0, {NX}])")

geometry_lines = "\n".join(
    f"    nodes[{a}:{b}, {y}] = LAND;" for (a, b, y) in spans)

program = f"""// 2D flow past the island of Madeira -- D2Q9 BGK, Zou-He open boundaries.
//
// The obstacle is the real Madeira coastline (ETOPO 2022), rasterized by
// gen_flow_past_madeira.py into the {len(spans)} run-length `nodes` statements
// at the end of the geometry block, in its normal map orientation (north
// up).  The inflow enters through the top (northern) row at {AZ_DEG} deg off
// north -- the NNE trade wind that produces the famous Madeira vortex
// streets -- and leaves through a zero-gradient outflow at the bottom;
// the east-west boundaries are periodic.  The Karman street trails to
// the SSW, as in the satellite images.
//
// Physical analog: the ATMOSPHERIC island wake.  Madeira's terrain
// (1862 m) pierces the trade inversion (~800-1500 m), so the cloud-topped
// marine boundary layer flows around (not over) the island and behaves
// quasi-two-dimensionally.  The sea-level coastline used here stands in
// for the terrain contour at inversion height, and Re = {U_IN * out_w / NU:.0f} (on the
// island's {out_w}-cell E-W extent) is a laboratory-scale stand-in for the
// effective large-eddy Reynolds number of the real flow.  The slower
// oceanic wake (Canary Current) is NOT what this setup models.
//
// Boundary-condition structure and numerics are identical to
// flow_past_cylinder_2d_bgk_zouhe.gelb (the validation anchor).
//
// Run (from the gelb repo root; ~4-10 min on a modern multicore CPU):
//   ./scripts/gelb-run -b cpu_highway -n 250000 -w 10000 \\
//       examples/softwarex-2026-paper/flow_past_madeira_2d_bgk_zouhe.gelb
//
// D2Q9 velocity index convention:
//   0: rest    1: E    2: N    3: W    4: S
//   5: NE      6: NW   7: SW   8: SE

simulation_description("2D flow past Madeira, Zou-He inlet/outlet (LBM-BGK, D2Q9)");

global_constants {{
    const int NX = {NX};               // east-west (periodic)
    const int NY = {NY};              // north-south (inlet top, outlet bottom)
    const real TAU = {TAU};           // nu = (TAU - 0.5)/3 = 1/75
    const real TAU_INV = 1.0 / TAU;

    const real U_IN = {U_IN};          // inflow speed, Ma ~ 0.087
    const real U_INX = {U_INX:.6f};    // = -U_IN * sin({AZ_DEG} deg)  (NNE wind)
    const real U_INY = {U_INY:.6f};    // = -U_IN * cos({AZ_DEG} deg)

    const real PI = 3.14159265358979;
    const array[real, 9] EX = {{0.0, 1.0, 0.0, -1.0,  0.0, 1.0, -1.0, -1.0,  1.0}};
    const array[real, 9] EY = {{0.0, 0.0, 1.0,  0.0, -1.0, 1.0,  1.0, -1.0, -1.0}};
    const array[real, 9] W = {{4.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0, 1.0/9.0,
                              1.0/36.0, 1.0/36.0, 1.0/36.0, 1.0/36.0}};
}}

lattices {{
    lattice f(2, 9, real, {{NX, NY}}, {{true, false}});
}}

function Macro(array[real, 9] fIn) -> (real rho, real ux, real uy) {{
    rho = sum(fIn);
    ux = dot_prod(EX, fIn) / rho;
    uy = dot_prod(EY, fIn) / rho;
}}

function Eq(real rho, real ux, real uy) -> (array[real, 9] feq) {{
    real usq = ux*ux + uy*uy;
    array[real, 9] eu = EX * ux + EY * uy;
    feq = W * rho * (1.0 + 3.0*eu + 4.5*eu*eu - 1.5*usq);
}}

// Uniform free stream plus a small transverse perturbation that seeds
// the shedding instability (the irregular coastline breaks symmetry on
// its own; the perturbation just shortens the onset transient).
initializer InitFluid {{
    real ux0 = U_INX + 0.05 * U_IN * sin(6.0 * PI * real(y) / real(NY));
    f.out[x, y | :] = Eq(1.0, ux0, U_INY);
}}

// Coast cells start at REST equilibrium so every lattice slot a coast
// cell might copy from (including LAND interior neighbors) holds a
// finite, zero-momentum value.
initializer InitWall {{
    f.out[x, y | :] = W;
}}

dynamic FluidDynamic {{
    array[real, 9] fIn = upstream_dfs(f, x, y, {{EX, EY}});
    real rho;
    real ux;
    real uy;
    {{rho, ux, uy}} = Macro(fIn);
    f.out[x, y | :] = fIn - TAU_INV * (fIn - Eq(rho, ux, uy));
}}

// Zou-He velocity inlet at the top row (y = NY-1): prescribe
// u = (U_INX, U_INY) with U_INY < 0 (inflow, southward).  Post-streaming
// knowns are 0,1,3 (same row) and 2,5,6 (from the row below); the
// unknowns 4 (S), 7 (SW), 8 (SE) are reconstructed from mass and
// momentum plus the non-equilibrium bounce-back closure on the normal
// direction, then the node collides like any bulk node.
dynamic ZouHeInlet {{
    real f0 = f.in[x,     y     | 0];
    real f1 = f.in[x - 1, y     | 1];
    real f3 = f.in[x + 1, y     | 3];
    real f2 = f.in[x,     y - 1 | 2];
    real f5 = f.in[x - 1, y - 1 | 5];
    real f6 = f.in[x + 1, y - 1 | 6];

    real rho_in = (f0 + f1 + f3 + 2.0 * (f2 + f5 + f6)) / (1.0 + U_INY);
    real nxd = 0.5 * (f1 - f3);
    real f4 = f2 - (2.0 / 3.0) * rho_in * U_INY;
    real f7 = f5 + nxd - (1.0 / 6.0) * rho_in * U_INY - 0.5 * rho_in * U_INX;
    real f8 = f6 - nxd - (1.0 / 6.0) * rho_in * U_INY + 0.5 * rho_in * U_INX;

    array[real, 9] fIn = {{f0, f1, f2, f3, f4, f5, f6, f7, f8}};
    real rho;
    real ux;
    real uy;
    {{rho, ux, uy}} = Macro(fIn);
    f.out[x, y | :] = fIn - TAU_INV * (fIn - Eq(rho, ux, uy));
}}

// Zero-gradient outflow at the bottom row (y = 0): the node copies
// its upstream neighbor's post-collision state, i.e. d f / d y = 0.
// A pressure (Zou-He density) outlet is too reflective for a vortex
// street: clamping rho at the boundary while the wake convects
// through it drives a spurious recirculating state.
dynamic Outflow {{
    f.out[x, y | :] = f.in[x, y + 1 | :];
}}

// Half-way bounce-back on the coastline ring: each slot i is loaded
// with the neighboring cell's post-collision DF pointing back along
// -e_i, so when that fluid neighbor pulls slot i on the next step it
// receives its own reflected population -- the no-slip coastline sits
// half a link outside the ring, and every fluid-facing link conserves
// mass exactly.
// (Slots whose neighbor is another COAST/LAND cell copy rest-state
// values; they are never pulled by fluid cells.)
dynamic BounceBack {{
    f.out[x, y | :] = bounce_back_dfs(f, x, y, {{EX, EY}});
}}

gauge Hydro -> (real rho, real ux, real uy) {{
    {{rho, ux, uy}} = Macro(f.in[x, y | :]);
}}

node_classes {{
    node_class FLUID(InitFluid, FluidDynamic, Hydro);
    node_class INLET(InitFluid, ZouHeInlet, Hydro);
    node_class OUTLET(InitFluid, Outflow, Hydro);
    node_class COAST(InitWall, BounceBack, Hydro);
    node_class LAND(InitWall) masked;
}}

geometry {{
    nodes[:, :] = FLUID;
    nodes[:, 0] = OUTLET;
    nodes[:, NY - 1] = INLET;
{geometry_lines}
    border(LAND) = COAST;
}}
"""

out_path = os.path.join(_here, "flow_past_madeira_2d_bgk_zouhe.gelb")
with open(out_path, "w") as fh:
    fh.write(program)
print(f"wrote {out_path}")
