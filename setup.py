#!/usr/bin/env python3
""" GeLB is a domain-specific language for Lattice Boltzmann (LB/LBM) simulations.

It provides:

- clear domain abstractions
- easy access to the core algorithm
- built-in consistency checks
- code-generation for multiple hardware architectures (currently: for CPUs and
  GPUs; in the future: also for FPGAs)
- and much more

The primary audience for this package consists of students, researchers and
tinkerers interested in LBM.

This module provides the reference compiler for the GeLB language, which is
distributed under the terms of the Mozilla Public License 2.0 (MPL-2.0).
"""
DOCLINES = (__doc__ or '').split("\n")

# TODO add more code here, to get the packaging in a functional state
#      REFs: - modern guides on Python packaging & release via PyPI
#            - setup.py from well-known packages (numpy?)
