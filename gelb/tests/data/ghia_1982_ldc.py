"""Reference centerline data from Ghia, Ghia & Shin (1982).

Citation
--------
U. Ghia, K. N. Ghia, C. T. Shin (1982).
*High-Re solutions for incompressible flow using the Navier-Stokes
equations and a multigrid method.*
Journal of Computational Physics 48: 387-411.
DOI: 10.1016/0021-9991(82)90058-4

These are the canonical reference values for 2-D lid-driven cavity
flow.  They are tabulated at non-uniform y- and x-locations
matching the 129x129 grid used in Ghia's multigrid solution.

Conventions
-----------
- Cavity is the unit square ``(x, y) in [0, 1]^2`` with the lid (top
  wall) moving at uniform velocity ``U`` along ``+x``.
- ``u`` is sampled along the **vertical centerline** at ``x = L/2``;
  values are normalised by ``U``.
- ``v`` is sampled along the **horizontal centerline** at ``y = L/2``;
  values are normalised by ``U``.
- ``y/L`` and ``x/L`` follow Ghia's grid sampling (17 points each).

Important
---------
This data module was transcribed by an AI language model from
recall of Tables I-II of Ghia et al. (1982), not copied from the
printed tables.  **Verify each value
against the original paper before using these numbers in a
manuscript or comparing them as a passing-grade benchmark.**  The
numerical values themselves are factual results (not subject to
copyright); only the transcription accuracy needs review.

Usage
-----
    from gelb.tests.data.ghia_1982_ldc import GHIA_RE_100, GHIA_RE_1000

    y_norm = GHIA_RE_100["y_over_L"]    # array, length 17
    u_norm = GHIA_RE_100["u_over_U"]    # array, length 17

    x_norm = GHIA_RE_100["x_over_L"]    # array, length 17
    v_norm = GHIA_RE_100["v_over_U"]    # array, length 17
"""

from __future__ import annotations


GHIA_RE_100 = {
    "Re": 100,
    # Table I -- u along vertical centerline (x = L/2).
    "y_over_L": [
        0.0000, 0.0547, 0.0625, 0.0703, 0.1016, 0.1719,
        0.2813, 0.4531, 0.5000, 0.6172, 0.7344, 0.8516,
        0.9531, 0.9609, 0.9688, 0.9766, 1.0000,
    ],
    "u_over_U": [
         0.00000, -0.03717, -0.04192, -0.04775, -0.06434, -0.10150,
        -0.15662, -0.21090, -0.20581, -0.13641,  0.00332,  0.23151,
         0.68717,  0.73722,  0.78871,  0.84123,  1.00000,
    ],
    # Table II -- v along horizontal centerline (y = L/2).
    "x_over_L": [
        0.0000, 0.0625, 0.0703, 0.0781, 0.0938, 0.1563,
        0.2266, 0.2344, 0.5000, 0.8047, 0.8594, 0.9063,
        0.9453, 0.9531, 0.9609, 0.9688, 1.0000,
    ],
    "v_over_U": [
         0.00000,  0.09233,  0.10091,  0.10890,  0.12317,  0.16077,
         0.17507,  0.17527,  0.05454, -0.24533, -0.22445, -0.16914,
        -0.10313, -0.08864, -0.07391, -0.05906,  0.00000,
    ],
}


GHIA_RE_1000 = {
    "Re": 1000,
    # Table I -- u along vertical centerline (x = L/2).
    "y_over_L": GHIA_RE_100["y_over_L"],  # same y-sampling
    "u_over_U": [
         0.00000, -0.18109, -0.20196, -0.22220, -0.29730, -0.38289,
        -0.27805, -0.10648, -0.06080,  0.05702,  0.18719,  0.33304,
         0.46604,  0.51117,  0.57492,  0.65928,  1.00000,
    ],
    # Table II -- v along horizontal centerline (y = L/2).
    "x_over_L": GHIA_RE_100["x_over_L"],  # same x-sampling
    "v_over_U": [
         0.00000,  0.27485,  0.29012,  0.30353,  0.32627,  0.37095,
         0.33075,  0.32235,  0.02526, -0.31966, -0.42665, -0.51550,
        -0.39775, -0.33340, -0.27224, -0.21388,  0.00000,
    ],
}


# Convenient lookup by Re.
GHIA_BY_RE = {
    100: GHIA_RE_100,
    1000: GHIA_RE_1000,
}


__all__ = ["GHIA_RE_100", "GHIA_RE_1000", "GHIA_BY_RE"]
