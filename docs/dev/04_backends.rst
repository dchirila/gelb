========
Backends
========

``gelbc --backend`` accepts ``cpu_fortran_serial``, ``cpu_highway``
(the default) and ``gpu_cuda_cpp`` (the ``click.Choice`` in
:source:`gelb/gelbc.py`).  Each generator takes the AST, the run
parameters and the ``BackendContext`` from ``build_backend_context``
in :source:`gelb/compiler_pipeline.py`, and returns the target program
as one string, which ``gelbc`` writes to ``-o`` or to the input name
with the backend's extension.

The three generators
====================

``cpu_fortran_serial``
   ``generate_fortran`` and ``FortranCodeGenerator`` in
   :source:`gelb/backends/stage3_backend_cpu_fortran_serial.py` emit a
   single-threaded Fortran 90 program (``.f90``).
   :source:`gelb/backends/fortran/common.py` holds the timing and
   throughput report lines and
   :source:`gelb/backends/fortran/line_formatter.py` splits lines
   longer than 132 characters at token boundaries.  This is the only
   backend that supports ``--output-mode stdout`` (checked in
   ``gelbc.py`` and in ``gelb/scripts/gelb-run``).

``cpu_highway``
   ``generate_cpu_highway`` and ``HighwayCodeGenerator`` in
   :source:`gelb/backends/stage3_backend_cpu_highway.py` emit a C++17
   program (``.cpp``) with OpenMP loops and Google Highway SIMD.  The
   class is assembled from the mixins of :source:`gelb/backends/highway/`:
   ``expr.py`` (expressions and intrinsic calls), ``statements.py``
   (statements, lattice reads and writes, the streaming intrinsics),
   ``simd.py`` (vector bodies, peeled edges and scalar tails),
   ``layout.py`` (storage layout, allocation, halo updates),
   ``output.py`` (NetCDF and gauges) and ``common.py`` (type maps,
   identifier encoding, host probes).

``gpu_cuda_cpp``
   ``generate_cuda_cpp`` and ``CudaCppCodeGenerator`` in
   :source:`gelb/backends/stage3_backend_gpu_cuda_cpp.py` emit CUDA C++
   (``.cu``).  The class subclasses ``HighwayCodeGenerator`` with
   ``use_openmp=False`` and ``storage_layout='soa'`` and adds the
   mixins of :source:`gelb/backends/cuda/`: ``device.py`` (device
   storage and cuRAND state), ``kernels.py`` (the ``__global__``
   kernels), ``launch.py`` (launch configuration, the time loop, CUDA
   graphs) and ``tiling.py`` (``--cuda-tiled``, ``--cuda-ldg``,
   ``--cuda-stwt``).  Expression and statement emission are inherited,
   so a change in ``highway/expr.py`` reaches the CUDA output.

Shared by more than one generator: :source:`gelb/backends/gauge_outputs.py`
(the gauge fields of the NetCDF file) and
:source:`gelb/backends/string_literals.py` (quoting) by all, and
:source:`gelb/backends/real_literals.py` by the C++ ones.

Runtime headers
===============

The C++ programs include a header (``runtime_header`` on each
generator class, emitted by ``_emit_includes``) rather than carrying
their helpers inline.  :source:`gelb/backends/cpu_highway_runtime.hpp`
and :source:`gelb/backends/gpu_cuda_cpp_runtime.cuh` both include
:source:`gelb/backends/cpp_runtime_common.hpp`, which holds the NetCDF
wrappers and the scalar reduction and ``min``/``max`` helpers; the
Highway header adds the vector overloads, the CUDA header the
``CUDA_CHECK`` macro and the event timer.  The Fortran program is
self-contained.  With ``--strict-fp``, ``_emit_includes`` writes
``#define GELB_STRICT_FP 1`` before the include, and
``cpu_highway_runtime.hpp`` then defines ``gelb_mul_add`` as a
separate multiply and add instead of ``hn::MulAdd``.

How ``gelb-run`` compiles the generated code
=============================================

:source:`gelb/scripts/gelb-run` translates with ``gelbc`` (``env
VIRTUAL_ENV= uv run --project <checkout> gelbc``, or ``$GELB_PYTHON -m
gelb.gelbc`` when ``GELB_PYTHON`` is set, which the script does itself
from the checkout's ``.venv/bin/python`` when ``uv`` is not found),
compiles with the ``compile_src`` of the
chosen backend's ``case`` branch, runs the executable (behind
:source:`gelb/visualization/progress_monitor.py` when a NetCDF run has
more than one time step) and removes the intermediates unless
``--keep`` is given.  The native compilers and their defaults:

- ``cpu_fortran_serial``: ``GELB_FC`` (default ``gfortran``) with
  ``GELB_FFLAGS`` (default ``-O3 -march=native -ffp-contract=off
  -fno-range-check -ffree-line-length-none``) and the NetCDF-Fortran
  flags ``GELB_NETCDF_INC`` and ``GELB_NETCDF_LIB`` (detected with
  ``nf-config`` and ``nc-config`` when unset).
- ``cpu_highway``: ``GELB_CXX`` (default ``g++`` on Linux; on macOS
  the first of ``g++-16`` to ``g++-13``, else ``clang++`` with the
  OpenMP runtime from ``GELB_OMP_ROOT`` or Homebrew's ``libomp``) with
  ``GELB_CXXFLAGS`` (default ``-std=c++17 -O3 -march=native
  -ffp-contract=off -fno-trapping-math -fno-unroll-loops -DNDEBUG``,
  with ``-mcpu=native`` in place of ``-march=native`` for Apple clang
  on arm64; OpenMP flags appended), ``-I`` for ``third_party/highway`` and
  ``gelb/backends``, four Highway support ``.cc`` files compiled in,
  and NetCDF-C from ``GELB_NETCDF_C_ROOT`` or ``GELB_NETCDF_C_INC``
  and ``GELB_NETCDF_C_LIB`` (``nc-config`` when unset).  At run time
  it fills in ``OMP_NUM_THREADS`` (physical cores) and, on Linux,
  ``OMP_PROC_BIND`` and ``OMP_PLACES``, each only when unset.
- ``gpu_cuda_cpp``: ``GELB_NVCC`` (default ``nvcc``) with
  ``GELB_NVCC_ARCH`` (default ``-arch=sm_89``) and ``GELB_NVCC_FLAGS``
  (default ``-O3 $NVCC_ARCH -std=c++17 --expt-relaxed-constexpr
  -DNDEBUG -diag-suppress=177``), plus the same NetCDF-C variables.

``-F`` appends the compiler's fast-math flag; ``--strict-fp`` passes
``--strict-fp`` to ``gelbc``, appends ``-ffp-contract=off`` (CPU) or
``-fmad=false`` (nvcc), and rejects ``-F`` and any override carrying a
value-changing flag (``reject_value_changing_flags``).
``GELBC_EXTRA`` forwards extra ``gelbc`` options.  ``gelbc`` itself
reads ``GELB_CXX``, ``GELB_CXXFLAGS`` and ``GELB_HAS_AVX512`` to detect
AVX-512, which decides the ``cpu_highway`` storage layout
(:doc:`07_design_decisions`).

What the backends must agree on
===============================

The user tutorial's chapter *Numerical Semantics*
(:source:`docs/user/19_numerical_semantics.rst`) is the authoritative
statement; its table *What must agree* says which results are bitwise
identical between a default and a plain build, and across backends in
strict and in default builds: the IEEE basic operations (in strict
builds), folded constants, ``min``, ``max``, ``mod`` and integer
powers agree across backends, while real powers, reductions and
library functions may differ.  :source:`gelb/tests/numeric/` enforces it against an
independent C++ oracle: ``cases.py`` generates the corpus,
:source:`gelb/tests/numeric/conftest.py` compiles the oracle with
``-O0 -fno-fast-math -ffp-contract=off``,
``test_generated_constants.py`` checks the folded constants, and
``test_generated_runtime.py`` builds every runtime case (those not
marked ``runtime=False`` in ``cases.py``) on all three backends
through ``gelb-run`` in an ``optimized`` and a ``plain`` mode
(``MODES``) and compares bit for bit (``checks.py``).
:source:`gelb/tests/integration/test_real_width_contract.py`,
:source:`gelb/tests/integration/test_reproducibility.py` and
:source:`gelb/tests/integration/test_math_library_accuracy.py` cover
the build modes, reproducibility across execution configurations and
library accuracy, as the chapter's notes name them.
