#!/usr/bin/env python3

"""
GeLB is a domain-specific language for Lattice Boltzmann (LB/LBM) simulations.

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

from setuptools import setup, find_packages

setup(
    name="gelb",
    description=DOCLINES[0],
    long_description="\n".join(DOCLINES[2:]),
    author="Dragos B. Chirila",
    license="MPL-2.0",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "antlr4-python3-runtime>=4.13.2",
        "antlr4-tools>=0.2.1",
        "click>=8.1.7",
        "colorama>=0.4.6",
        "Jinja2>=3.1.4",
        "numpy>=1.26.4",
        "sympy>=1.12",
        "matplotlib>=3.8.0",
        "netcdf4>=1.6.5",
    ],
    extras_require={
        'dev': [
            'pytest>=8.2.2',
            'setuptools>=70.0.0',
            'packaging>=24.0',
            'pluggy>=1.5.0',
            'iniconfig>=2.0.0',
        ],
    },
    entry_points={
        'console_scripts': [
            'gelbc=gelb.gelbc:cli',
        ],
    },
)
