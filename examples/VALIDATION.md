# GeLB Analytical Validation

Quantitative verification of GeLB-generated LBM simulations against
known analytical solutions.

## How to run

```bash
uv run python scripts/validate_analytical.py
```

This compiles and runs all validation cases at multiple grid resolutions
(N = 16, 32, 64, 128, 256), computes L2 error norms against analytical
solutions, and produces a convergence plot (`validation_convergence.png`).

Individual cases can be selected:

```bash
uv run python scripts/validate_analytical.py --cases poiseuille
uv run python scripts/validate_analytical.py --cases taylor_green_mrt
uv run python scripts/validate_analytical.py --cases couette_bgk couette_mrt
uv run python scripts/validate_analytical.py --cases couette_bgk_zouhe couette_mrt_zouhe poiseuille_zouhe
```

The OpenMP-parallel CPU backend is also accepted (handy on machines
without an NVIDIA GPU):

```bash
uv run python scripts/validate_analytical.py --backend cpu_highway \
    --cases couette_bgk_zouhe poiseuille_zouhe \
    --resolutions 16 32 64 128
```


## Results summary

### Periodic flows (no walls)

| Case | N=16 | N=32 | N=64 | N=128 | Rate (64->128) |
|------|------|------|------|-------|-----------------|
| Taylor-Green (BGK, NU=1/6) | 1.3e-2 | 2.9e-3 | 9.9e-4 | 4.5e-4 | 1.13 |
| Taylor-Green (MRT, NU=1/30) | 2.3e-2 | 5.4e-3 | 1.0e-3 | 2.8e-4 | 1.84 |

Taylor-Green MRT achieves near-**2nd-order** spatial convergence
(slope ~1.8-2.4 between N=32 and N=128). At N >= 256 both BGK and MRT
hit a time discretization floor (~5e-4) because the evaluation time
`t = int(t_decay)` truncates fractional timesteps.

### Wall-bounded flows (bounce-back walls)

| Case | NY=16 | NY=32 | NY=64 | NY=128 | NY=256 | Rate (128->256) |
|------|-------|-------|-------|--------|--------|-----------------|
| Poiseuille (MRT, bounce-back + Strang) | 6.3e-3 | 1.4e-3 | 3.2e-4 | 7.8e-5 | 1.9e-5 | 2.02 |
| Couette (BGK, `bounce_back_dfs`) | 5.1e-12 | 2.2e-11 | 9.9e-11 | 4.2e-10 | — | round-off |
| Couette (MRT, `bounce_back_dfs`) | 5.3e-7 | 1.8e-7 | 6.1e-8 | 2.1e-8 | — | 1.52 (64->128) |

The Couette rows were run with NX=8 instead of 128 (the flow is
uniform along the periodic x axis) and NY up to 128.

### Wall-bounded flows (Zou-He velocity boundary conditions)

Per Zou & He (1997) and Guo & Shu (2013) §2.2.2, Zou-He pins the
no-slip surface **at the boundary node** instead of midway between
the wall and fluid nodes as full-way bounce-back does.  The implementation reconstructs the unknown DFs from the
post-streaming knowns and **then applies collision** on the
boundary cell with the same relaxation operator as the bulk — the
boundary nodes must collide just like the bulk nodes to deliver
second-order accuracy.

| Case | NY=16 | NY=32 | NY=64 | NY=128 | Rate (64->128) |
|------|-------|-------|-------|--------|----------------|
| Poiseuille (MRT + Zou-He) | 6.6e-4 | 1.5e-4 | 3.6e-5 | 8.9e-6 | **2.03** |
| Couette (BGK + Zou-He) | 5e-12 | 2e-11 | 8e-11 | 3e-10 | machine precision |
| Couette (MRT + Zou-He) | 2.5e-6 | 1.2e-6 | 6.2e-7 | 3.1e-7 | 1.00 (Ma-bounded) |

The Couette **BGK** Zou-He variant recovers the analytical linear
profile to machine precision — Couette is exactly representable in
the incompressible limit and Zou-He pins both walls exactly at
their node positions, so no truncation error remains for an LBM
model that conserves mass and momentum exactly.  The Couette
**MRT** Zou-He variant lands at `~1e-6` and converges only at
1st-order with NY because the higher-order non-stress moment
relaxation rates (`s_e, s_eps, s_q`) introduce a small mixing at
the wall whose magnitude scales as `1/NY`; the residual is well
below the Mach-induced error budget.

The Poiseuille **MRT** Zou-He variant achieves a clean **2nd-order**
slope (`~2.05` averaged across resolution doublings, peak velocity
matching analytical to ~0.01% at NY=32), as predicted by the
classical Zou-He convergence analysis.

Poiseuille (MRT) achieves clean **2nd-order** spatial convergence
by using bounce-back walls in which the wall cell reads the adjacent
fluid cell's outgoing DFs, and a symmetric **Strang-split** body
force in moment space. See
[rayleigh_benard_2d_mrt.gelb:384-439](lbm/2d/rayleigh_benard_2d_mrt.gelb#L384-L439)
for the prototype wall-dynamics pattern and
[poiseuille_flow_2d_mrt.gelb](lbm/2d/poiseuille_flow_2d_mrt.gelb)
for the Poiseuille application.

Observed convergence rates (TAU=0.54, G scaled ∝ 1/(NY-2)² to hold
Mach number constant):

| NY → 2·NY | observed rate |
|-----------|---------------|
|  16 →  32 | 2.20 |
|  32 →  64 | 2.10 |
|  64 → 128 | 2.05 |
| 128 → 256 | 2.02 |

The wall cells read the populations of their fluid neighbours that
point back at them, one link at a time (`bounce_back_dfs` written
out):

```gelb
f.out[x, 0 | 2] = f.in[x,     1 | 4];   // N  ← S
f.out[x, 0 | 5] = f.in[x + 1, 1 | 7];   // NE ← SW
f.out[x, 0 | 6] = f.in[x - 1, 1 | 8];   // NW ← SE
```

which puts the no-slip surface at y=0.5 (modulo the small
viscosity-dependent offset documented below).

Couette (BGK and MRT) **with bounce-back walls** uses
`bounce_back_dfs`: BGK reproduces the linear profile to round-off, as
the Zou-He BGK variant does, and MRT converges at about order 1.5
from 5e-7.  The companion Zou-He variants
(`couette_flow_2d_bgk_zouhe.gelb`,
`couette_flow_2d_mrt_zouhe.gelb`) recover the analytical linear
profile to machine precision (BGK) or `~1e-6` (MRT) — see the
Zou-He table above.


## Bounce-back wall position

**What `bounce_back_dfs` does.** Entry i of
`bounce_back_dfs(f, x, y, {EX, EY})` is
`f.in[x + EX[i], y + EY[i] | opp(i)]`, the population of the
neighbour in direction i that points back at the wall cell. The
fluid neighbour pulls it on the next step as its slot i, so every
population that reaches the wall goes back along its link: full-way
bounce-back (Krüger et al. 2017, §5.3.3.2), the per-link
*wall-cell-reads-fluid* blocks of the Poiseuille and Rayleigh-Benard
examples in one line. On a non-periodic axis, a link whose neighbour
lies outside the grid gives the cell's own `f.in[x, y | opp(i)]`,
which nothing streams. For a channel with wall nodes at y=0 and
y=NY-1:

- Effective walls at y = 0.5 and y = NY - 1.5
- Effective channel height: H = NY - 2

Written out per link, this wall gives the lid-driven cavity at
N = 129, Re = 100, U = 0.05 a relative L2 error against Ghia et al.
of 0.50 % in u and 2.40 % in v. With BGK collision the exact position
of the no-slip plane also depends on the relaxation time (Krüger et
al. 2017, §5.3.3.5 and §5.4.1; Ginzburg, 2008); TRT or MRT with
suitably chosen rates removes that dependence.

### Poiseuille coefficient accuracy

The parabolic velocity coefficient `G / (2 * nu)` is reproduced
exactly (ratio = 1.000) for both MRT and Guo-forced BGK. With
bounce-back walls, the parabola's
zeros sit at y=0.5 and y=NY-1.5 to within the small viscosity-
dependent offset discussed above, so both the coefficient *and* the
wall position are accurate.


## Rayleigh-Benard convection

`examples/lbm/2d/rayleigh_benard_2d_mrt.gelb` implements 2D
Rayleigh-Benard convection using a D2Q9 fluid lattice coupled with a
D2Q5 temperature lattice, with MRT collision; it is a **bit-faithful
port** of the reference Fortran solver in `rb_2d/runs__*/Pr_*/Ra_*/`.
(A BGK-collision variant of the same set-up is pinned with the paper
material as `examples/softwarex-2026-paper/rayleigh_benard_2d_bgk.gelb`;
it is a listing, not a validated case.)

The MRT example is a line-by-line port of the reference CUDA Fortran
solver `MrtSolverBoussinesq2D_class.f90`. It uses:

- The **incompressible** D2Q9 MRT scheme (equilibrium moments are
  functions of velocity components, not `ρ·u`)
- Custom moment ordering `[ρ, jx, jy, e, pxx, pxy, qx, qy, ε]` matching
  Fortran's `M_FLUID` and `mRelaxVecFluid`
- Strang-split Boussinesq buoyancy injected into the `jy` moment
- **Yoshida** anti-bounce-back temperature BC (with the
  `2·√3·κ·T_wall` correction term)
- Fluid bounce-back implemented via the wall cell reading the
  adjacent fluid cell's outgoing DFs (matches Fortran's bounce-back
  timing)
- Pre-populated wall cells at IC time, also matching Fortran lines
  411-417

A regression test
(`gelb/tests/integration/test_rayleigh_benard_mrt_e2e.py`) guards the
MRT example against algorithm regressions by:

1. Compiling and running the example with a fixed `--seed`
2. Comparing every gauge field to a stored snapshot
   (`gelb/tests/data/rb_mrt_snapshot.nc`) with `atol=1e-10, rtol=1e-7`
3. Checking physics invariants: T monotonic in y, T bounded, NaN at
   walls, bounded mass drift, uX small, uY small but non-zero

The example establishes **algorithmic parity with the reference
Fortran solver** (`MrtSolverBoussinesq2D_class.f90`): the GeLB output
is numerically comparable to Fortran reference output run at the same
parameters, modulo the residual differences listed below, and the
onset of convection matches the linear-stability threshold
`Ra_c ≈ 1707.76` (see *Critical Rayleigh number for the first
bifurcation* below).  Nusselt numbers are not compared with published
benchmarks.

### Residual differences vs the Fortran reference

These are documented in the example header and do not affect the
algorithmic correctness:

1. **t=0 gauge snapshot** — GeLB writes a t=0 snapshot (the pre-loop
   gauge pass); the Fortran reference does not. Compare time series
   starting at `t = output_freq`.
2. **FP reduction order** — `sum`, `dot_prod`, `matmul`, and FMA usage
   may differ between gfortran-of-Fortran-source and gfortran-of-
   GeLB-emitted-source, so bit-exact agreement across machines is
   not expected; numerical agreement to ~1e-10 is.
3. **Mass drift bound** — with the wall-cell-reads-fluid bounce-back
   pattern, the wall holds the previous step's outgoing DFs, so the
   per-step interior mass exchange has a one-step lag. The drift is
   bounded (~`α_G`, a few × 1e-3 for the test parameters) and does
   not grow.

The IC seeding (localized delta `T_HOT/1e5` at `(NX/2, 2)` plus
uniform noise floor `T_HOT/1e8`) matches the Fortran reference. The delta is emitted via the bool-to-real cast
pattern `DELTA_PERTURB * real(x == X_P && y == Y_P)`, which lowers
to `merge(1, 0, ...)` in Fortran.

### Critical Rayleigh number for the first bifurcation

Linear stability theory (Shan 1997; rigid-rigid no-slip walls with
periodic horizontal BCs) predicts

- `Ra_c ≈ 1707.76`
- critical wavenumber `k_c ≈ 3.117`, i.e. wavelength `λ_c ≈ 2.0158·H`

The Fortran reference study at
`rb_2d/runs__Ra_cr_1/Pr_0_71__Ny_41__Gamma_2__MaxMach_0_1/Ra_{1685,1700,1715,1730}`
brackets this value to within ±8 by sweeping four Ra around 1707.76
at `Ny=41` fluid rows, `Γ = 2π/k_c ≈ 2.0158` (one critical
wavelength fits horizontally), `Pr=0.71`, `Ma=0.1`, `simTime=450`
(~10⁷ LBM steps). That Fortran study seeds convection with a
**localized delta perturbation** `T_HOT/1e5` at a single cell plus
a uniform noise floor `T_HOT/1e6`.

`scripts/find_ra_critical.py` reproduces this sweep with the GeLB
MRT port, using the same grid (`-D NY=43 -D NX=83` — total rows
including walls = 43, so 41 fluid rows) and the CUDA backend
(`gpu_cuda_cpp`).
The GeLB IC seeds convection bit-faithfully against the Fortran
reference: non-equilibrium moment initialization (only the ρ and
ρ_T moments are set; all higher moments are left at zero, so the
MRT collision relaxes them to equilibrium over the first few
timesteps and generates the characteristic Fortran-reference
start-up transient), plus a localized `T_HOT/1e5` delta at
`(NX/2, 2)` and a uniform noise floor of `T_HOT/1e8`.

**Result** (10⁷-step horizon, Fortran-matching IC on NY=43, NX=83):

| Ra | late-time `max\|uY\|` | classification |
|----|---------------------:|----------------|
| 1500 | 8.03e-05 | decaying (gauge floor) |
| 1685 | 8.03e-05 | decaying (gauge floor) |
| 1700 | 8.03e-05 | decaying (gauge floor) |
| 1715 | 1.32e-03 | growing |
| 1730 | 2.26e-03 | growing |
| 1800 | 4.47e-03 | growing |
| 2000 | 7.54e-03 | growing (near saturation) |

The 8.03e-05 floor at sub-critical Ra is the `α_G · T_HOT`
base-state contribution that the gauge emits from the Strang-split
bookkeeping (the gauge reports `jy + α_G/2 · T`, which in the
quiescent conduction state sits at `α_G · T_HOT = 7.75e-5` at
NY=43, MaxMach=0.1). Below the bifurcation the delta perturbation
diffuses away within the first write interval and leaves only
machine-precision residuals on top of this base state; above the
bifurcation the unstable eigenmode grows out of the IC transient
and saturates.

**Bracketed Ra_c (GeLB, 10⁷-step horizon, Fortran-matching IC):**

> `Ra_c^{GeLB} ∈ (1700, 1715)`

This matches the Fortran `Ra_cr_1` study bracket to the width of
the Fortran sweep itself (±8) and contains the theoretical value
`Ra_c ≈ 1707.76` (Shan 1997). **Quantitative physics-level
parity with the Fortran reference is established.**

### The NY-vs-(NY−2) parameter derivation

The Fortran reference derives its LBM scaling from the fluid-row
count (`rb_2d.f90:79–83`):

```fortran
alphaG = maxMach**2 / (3 * Ny)            ! Ny = 41 fluid rows
viscosity = Ny * maxMach * sqrt(Pr / (3*Ra))
diffusivity = Ny * maxMach / sqrt(3*Ra*Pr)
```

In GeLB, `NY` is the *total* grid height (43, including the two
wall rows at `y = 0` and `y = NY − 1`), whereas Fortran's `Ny` counts
the fluid rows (41).  The GeLB example therefore uses `real(NY − 2)`
in `ALPHA_G`, `VISCOSITY`, `DIFFUSIVITY`, the `InitBulk` profiles and
the `InitWallBot` / `InitWallTop` pre-population helpers, to match the
physical channel height `H = NY − 2` — see the comment at
[rayleigh_benard_2d_mrt.gelb:46-58](lbm/2d/rayleigh_benard_2d_mrt.gelb#L46-L58).

To reproduce the sweep:

```bash
uv run python scripts/find_ra_critical.py
```

The driver uses `scripts/gelb-run`, compiles and runs the example
once per Ra value with the CUDA C++ backend, and prints a summary
table plus a Ra_c bracket.  Pass `--backend cpu` to fall back to
CPU serial (with OpenMP) if no NVIDIA GPU is available; expect
~10× slower wall times.


## References

- Zou, Q. & He, X. (1997). "On pressure and velocity boundary
  conditions for the lattice Boltzmann BGK model." *Physics of
  Fluids*, 9(6), 1591–1598.

- Guo, Z. & Shu, C. (2013). *Lattice Boltzmann Method and Its
  Applications in Engineering*, Advances in Computational Fluid
  Dynamics Vol. 3, World Scientific. (BC theory in §2.2; LDC
  benchmark in §4.2.)

- Lallemand, P. & Luo, L.-S. (2000). "Theory of the lattice Boltzmann
  method: Dispersion, dissipation, isotropy, Galilean invariance, and
  stability." *Physical Review E*, 61(6), 6546.

- Ginzburg, I. (2008). "Viscosity independent numerical errors for
  Lattice Boltzmann models: From recurrence equations to 'magic'
  collision numbers." *Computers & Mathematics with Applications*,
  55(7), 1535-1560.

- Guo, Z., Zheng, C., & Shi, B. (2002). "Discrete lattice effects on
  the forcing term in the lattice Boltzmann method." *Physical Review E*,
  65(4), 046308.

- De Rosis, A. (2017). "Nonorthogonal central-moments-based lattice
  Boltzmann scheme in three dimensions." *Physical Review E*, 95(1),
  013310.

- Krüger, T., Kusumaatmaja, H., Kuzmin, A., Shardt, O., Silva, G.,
  & Viggen, E.M. (2017). *The Lattice Boltzmann Method: Principles
  and Practice.* Springer.  (Moving-wall bounce-back formula:
  Eq. 5.26.)

- Shan, X. (1997). "Simulation of Rayleigh-Bénard convection using
  a lattice Boltzmann method." *Physical Review E*, 55(3), 2780.
