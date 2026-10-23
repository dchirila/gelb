# Colab notebooks

This directory holds Google Colab notebooks that run GeLB examples
end-to-end in the browser, no local install required.

## Notebooks

| File | Target | Runtime | What it does |
| --- | --- | --- | --- |
| `gelb_intro_2d.ipynb` | CPU (gfortran) | Free Colab CPU | Taylor-Green vortex decay on a 64×64 periodic D2Q9 grid; validates against the analytical `exp(-4νk²t)` kinetic-energy decay. **Start here** — the first-contact demo. ~70 lines of GeLB source. |
| `gelb_gpu_3d.ipynb` | GPU (nvcc, CUDA C++) | Colab GPU (T4) | Rayleigh-Bénard convection in 3-D with MRT collision and coupled D3Q19 fluid + D3Q7 temperature lattices. Advanced example (~555 lines of GeLB source) showcasing multi-lattice coupling, MRT, non-trivial wall BCs, and Strang-split buoyancy. |
| `paper_s3_1_convergence.ipynb` | CPU (gfortran) | Free Colab CPU | SoftwareX paper §3.1: grid convergence of the Taylor–Green vortex (BGK, MRT) and Poiseuille flow (MRT), plotted with the paper's values. 5–10 minutes. |
| `paper_s3_2_rayleigh_benard.ipynb` | CPU (gfortran) | Free Colab CPU | SoftwareX paper §3.2: 2-D Rayleigh–Bénard convection at Ra = 10⁴ with the MRT program (the paper's figure) and the BGK program (the paper's appendix listing). 3–6 minutes. |
| `paper_s3_3_karman_streets.ipynb` | GPU (nvcc, CUDA C++) | Colab GPU (T4) | SoftwareX paper §3.3: Kármán vortex streets behind a cylinder (Re = 150) and behind Madeira (Re = 300), the paper's two-panel figure. 15–20 minutes. |

The `paper_*` notebooks download their programs from
[`examples/softwarex-2026-paper/`](../examples/softwarex-2026-paper/) at the
`v1.0.0` tag and run them with the paper's step counts.

## Installation inside Colab

Each notebook installs GeLB 1.0.0 from its release tag on GitHub
(`pip install git+https://github.com/dchirila/gelb.git@v1.0.0`) and
sets `GELB_PYTHON` to the notebook's interpreter, which `gelb-run` uses
to start the compiler. A pip installation has no Highway library, so
the CPU notebooks select the Fortran backend (`-b cpu_fortran_serial`);
the default `cpu_highway` backend needs a source checkout.
