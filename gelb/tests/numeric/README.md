# Generated numeric conformance tests

These tests start with C++ expressions, compile an independent C++ reference,
translate the expressions to GeLB, and compare values. Agreement between GeLB's
backends alone cannot catch a bug in their shared frontend or optimizer.

The default corpus has **147 expressions**: 115 fixed boundary/type cases and
32 seeded compositions of eight expression families. It covers signed integer
division across all 16 width pairs and four sign combinations, float-to-integer
truncation, real32/real64 intermediate rounding, conversion after integer
arithmetic, comparisons, signed zero (including the zero identities
`u * 0.0`, `u + 0.0`, `0.0 - u` and a cancellation of two negated
operands), repeated real32 subtrees, subnormal results, and precision
boundaries at 2^24 and 2^53, literal conversion before algebra, the minimum
int64 literal, int64 coordinate arithmetic, direct integer-to-real32 rounding
above a binary32 midpoint, a nonzero cancellation input, a collapsed axis
(one cell) and a SIMD-sized program with a scalar tail (67 cells). This is
bounded, template-based generation, not a
complete language fuzzer or a proof that no arithmetic bugs remain.

## Run and reproduce

From the repository root:

```sh
uv run pytest -q -ra gelb/tests/numeric

# Fast frontend checks, with a native C++ oracle but no GeLB backend builds:
uv run pytest -q gelb/tests/numeric/test_generated_constants.py

# Show known defects as ordinary failures while fixing them:
uv run pytest -q --runxfail gelb/tests/numeric -k integer_quotient

# Retain sources, generated code, logs, manifests and JSON values:
uv run pytest -q gelb/tests/numeric --basetemp=/tmp/gelb-numeric-tests

# Expand the corpus or explore another deterministic seed:
GELB_NUMERIC_RANDOM_CASES=256 GELB_NUMERIC_SEED=0x1234 \
  uv run pytest -q gelb/tests/numeric
```

Pytest clears an existing `--basetemp` directory: use a disposable directory.
The seed and case ID reproduce an expression; `-k seed_d13d17_006` selects its
checks. Runtime checks share a batch build, so selecting one check still builds
the runtime corpus. A rejected batch is bisected to isolate the failing case,
allowing other cases to run. This isolates build failures; it does not attempt
general expression minimization.

Each mismatch prints the original C++, inputs, decimal and hexadecimal results,
and a standalone GeLB runtime reproducer. `numeric_reference*/reference.cpp`
contains the independent oracle. Per-backend directories retain GeLB sources,
generated target sources, commands, compiler logs and results. The harness
removes its executables, object/module files and NetCDF outputs after reading.

## What is checked

| Path | Default checks | Reference |
|---|---:|---|
| Typed constants and geometry predicates | 147 | Native result before final lattice storage |
| Constant-array literal, expression and alias substitution | 24 | Native input rounded to float, widened and reduced with zero |
| Translator, reproducibility and reference discriminators | 3 | Explicit syntax/value assertions |
| Runtime | 72 expressions x 4 forms x 2 optimization modes x 3 backends | Native result after storage conversion |

Runtime forms are a single-direction lattice write, a full Q=9 slice write, a
local-array declaration and a separate local-array assignment. Every cell of
the case's lattice is checked: four cells by default, one for the collapsed-axis
cases and 67 for the SIMD-sized all-real cases, whose Highway program is
asserted to enter the vector body. `plain` disables collinearity rewriting, scalar CSE
and slice simplification; `optimized` uses GeLB's defaults. Mixed lattice types
and a four-cell domain exercise scalar backend execution, **not Highway SIMD**.

The independent reference is compiled with `-O0 -fno-fast-math
-ffp-contract=off`; its input is volatile and its results are written as hex
floats. GeLB's generated programs use corresponding strict native compiler
flags. This isolates GeLB transformations from native reassociation and fused
multiply-add. The tests invoke the canonical compilation pipeline, assert that
constants actually became literals, and observe the resolved geometry map;
compiler helpers are never used to compute expected values.

Comparisons are bit-exact, including signed zero, on every path: the optimizer
applies only exact identities, folds literals in their own width, shares
identical ordered subtrees, and keeps a real zero's sign and a shared subtree's
width, so the optimized and plain modes agree with the native reference bit for
bit. The `reassociation_ulps` field stays
for a future family that needs it, at 0 today. Do not add a blanket relative
tolerance: it would hide the one-ULP conversion bugs near 2^24 and 2^53.

The translator accepts a restricted C++ subset: decimal/scientific literals,
`f` and `LL` suffixes, `u` and `x`, unary signs, parentheses, numeric
`static_cast`, arithmetic `+ - * /`, and comparisons. Unsupported syntax is an
error. C++ `float` maps to `real32`, `double` to `real`, `int64_t` to `int`, and
the other signed widths to their GeLB names. Constant runtime casts are hoisted
to typed global constants. Nonconstant explicit casts are checked in the
frontend corpus only; casting an entire GeLB array is outside this translator's
runtime subset. Signed division inputs fit every intermediate C++ and GeLB
integer type, despite their different narrow-integer promotion rules.

## Known defects

None are recorded. `known_failures.py` records only diagnosed cases, by
case name, expression, input, backend, mode and form, with `strict=True`; new
seeds/compositions are never marked automatically. A numerical expected
failure accepts only `NumericMismatch`, so a build failure cannot masquerade
as a known value error, and an unexpected pass fails the suite until the
obsolete entry is removed. The default matrix has no expected failures. The
generated tests are part of the Linux release-health workflow.

C++17 is required for the oracle. Backend tests additionally need their compiler
and NetCDF-C; existing toolchain guards skip unavailable backends. CUDA tests
also need a GPU and driver. This corpus does not cover real16, integer
overflow/wrapping, NaNs/infinities, undefined C++ operations, arbitrary
intrinsics, SIMD beyond the 67-cell cases, long simulations or periodic
addressing.
Those need their own generators and existing targeted integration tests.
