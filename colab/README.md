# Colab notebooks

This directory holds Google Colab notebooks that run GeLB examples
end-to-end in the browser, no local install required.

## Notebooks

| File | Target | Runtime | What it does |
| --- | --- | --- | --- |
| `gelb_intro_2d.ipynb` | CPU (gfortran) | Free Colab CPU | Taylor-Green vortex decay on a 64×64 periodic D2Q9 grid; validates against the analytical `exp(-2νk²t)` kinetic-energy decay. **Start here** — the first-contact demo. ~70 lines of GeLB source. |
| `gelb_gpu_3d.ipynb` | GPU (nvcc, CUDA C++) | Colab GPU (T4) | Rayleigh-Bénard convection in 3-D with MRT collision and coupled D3Q19 fluid + D3Q7 temperature lattices. Advanced example (~555 lines of GeLB source) showcasing multi-lattice coupling, MRT, non-trivial wall BCs, and Strang-split buoyancy. |

## Installation inside Colab

Each notebook starts with an "Install GeLB" cell covering the
supported install paths (see the cell's comments for details).
