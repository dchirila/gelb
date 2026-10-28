#!/usr/bin/env python3
"""
Measure lines-of-code savings: GeLB source vs generated backend code.

For every ``*.gelb`` under ``examples/`` (or another root), compile to
the CPU serial Fortran backend (``cpu_fortran_serial``) and/or the
CUDA backend and compare lines of code. Reports both raw ``wc -l``
counts and SLOC (non-blank, non-comment), aggregated size-weighted
across all examples and as per-example averages.

Why two different LOC metrics?

* **Raw** is what a developer sees scrolling the file, and is what most
  LOC-savings claims in the wild report. It is noisy, because the
  ratio of blank-and-comment lines to substantive code is not the
  same in GeLB sources and in generated Fortran.
* **SLOC** strips ``//`` and ``/* ... */`` comments from GeLB and
  ``!`` comments from Fortran, plus blank lines. This is the fair
  number for a paper -- it counts the code a developer actually writes
  and maintains.

Why both size-weighted and per-example averages?

* **Size-weighted** (``sum / sum``) treats the whole corpus as one
  big file. This is dominated by the large, realistic examples
  (Rayleigh-Benard, reduced-gravity ocean, 3D MRT) -- the cases where
  GeLB is meant to be used.
* **Mean / median per-example** treats every example equally, which
  flatters GeLB because tiny test programs have huge ratios
  (NetCDF/time-loop boilerplate dominates). This is the optimistic
  number. Reporting both -- with the size-weighted as the headline --
  is the honest way to do it.

Usage (from the project root):

    uv run python scripts/measure_loc_savings.py
    uv run python scripts/measure_loc_savings.py --examples examples/lbm
    uv run python scripts/measure_loc_savings.py --backend cpu
    uv run python scripts/measure_loc_savings.py --tsv loc.tsv

Requires ``uv``, a working GeLB install, and -- for ``--backend gpu`` or
``both`` -- a gelbc capable of emitting CUDA C++ (no nvcc
needed; we only count the generated source).
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from statistics import mean, median

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))


# ---------------------------------------------------------------------------
# LOC counting
# ---------------------------------------------------------------------------

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def count_loc_gelb(path):
    """Return (raw, sloc) for a GeLB source file.

    SLOC strips ``//`` line comments and ``/* ... */`` block comments
    (possibly multi-line, matching the GeLB grammar's hidden-channel
    rules) and then drops blank lines.
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    raw = len(text.splitlines())
    text = _BLOCK_COMMENT_RE.sub("", text)
    sloc = 0
    for line in text.splitlines():
        i = line.find("//")
        if i >= 0:
            line = line[:i]
        if line.strip():
            sloc += 1
    return raw, sloc


def count_loc_fortran(path):
    """Return (raw, sloc) for a Fortran (.f90) source file.

    SLOC strips everything after ``!`` on each line and then drops
    blanks. Generated backend code has no ``!`` inside string
    literals, so the naive rule is exact here.
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    raw = len(lines)
    sloc = 0
    for line in lines:
        i = line.find("!")
        if i >= 0:
            line = line[:i]
        if line.strip():
            sloc += 1
    return raw, sloc


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def compile_example(gelb_path, backend, out_path, num_timesteps):
    """Invoke ``uv run gelbc`` to transpile one example.

    Returns True on success, False on any nonzero exit (which we
    silently tolerate -- the example is dropped from the report with
    a warning on stderr).
    """
    cmd = [
        "uv", "run", "gelbc", gelb_path,
        "-o", out_path,
        "--num-timesteps", str(num_timesteps),
    ]
    if backend == "gpu":
        cmd += ["--backend", "gpu_cuda_cpp"]
    else:
        cmd += ["--backend", "cpu_fortran_serial"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Categorization
# ---------------------------------------------------------------------------

_CATEGORY_ORDER = ["basic", "LBM 1D", "LBM 2D", "LBM 3D", "LGCA", "other"]


def categorize(rel_path):
    parts = rel_path.replace(os.sep, "/")
    if "/basic/" in parts:
        return "basic"
    if "/lbm/1d/" in parts:
        return "LBM 1D"
    if "/lbm/2d/" in parts:
        return "LBM 2D"
    if "/lbm/3d/" in parts:
        return "LBM 3D"
    if "/lgca/" in parts:
        return "LGCA"
    return "other"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Row:
    path: str
    category: str
    gelb_raw: int
    gelb_sloc: int
    cpu_raw: int
    cpu_sloc: int
    gpu_raw: int
    gpu_sloc: int


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _expansion(gelb, other):
    """Return the expansion ratio ``other / gelb`` as a float, or None."""
    if gelb <= 0 or other <= 0:
        return None
    return other / gelb


def _fmt_ratio(ratio):
    return "—" if ratio is None else f"{ratio:.2f}\u00d7"


def _fmt_reduction(ratio):
    """Format ``1 - 1/ratio`` as a percent. ``ratio`` is expansion."""
    if ratio is None or ratio <= 0:
        return "—"
    return f"{100 * (1 - 1 / ratio):.1f}%"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(rows, do_cpu, do_gpu, out=sys.stdout):
    n = len(rows)
    emit = lambda s="": print(s, file=out)

    emit(f"# GeLB lines-of-code savings ({n} examples)")
    emit()
    emit("* **Raw** = all lines (blanks and comments included).")
    emit("* **SLOC** = non-blank, non-comment lines only "
         "(strips `//` and `/* */` in GeLB, `!` in Fortran).")
    emit("* **Size-weighted** = sum across all examples "
         "(dominated by large, realistic programs).")
    emit("* **Per-example** = mean/median of individual ratios "
         "(flattered by tiny test programs).")
    emit()

    sum_g_raw = sum(r.gelb_raw for r in rows)
    sum_g_sloc = sum(r.gelb_sloc for r in rows)
    sum_c_raw = sum(r.cpu_raw for r in rows)
    sum_c_sloc = sum(r.cpu_sloc for r in rows)
    sum_p_raw = sum(r.gpu_raw for r in rows)
    sum_p_sloc = sum(r.gpu_sloc for r in rows)

    # ----- headline -----
    emit("## Headline (size-weighted SLOC)")
    emit()
    if do_cpu:
        exp = _expansion(sum_g_sloc, sum_c_sloc)
        emit(f"* **CPU Fortran** — the backend writes {_fmt_ratio(exp)} the code a "
             f"GeLB developer writes. A GeLB program is "
             f"**{_fmt_reduction(exp)} shorter** than the equivalent CPU source.")
    if do_gpu:
        exp = _expansion(sum_g_sloc, sum_p_sloc)
        emit(f"* **CUDA C++** — backend expansion {_fmt_ratio(exp)}. "
             f"A GeLB program is **{_fmt_reduction(exp)} shorter** than "
             f"the equivalent CUDA source.")
    emit()

    # ----- size-weighted table -----
    emit("## Size-weighted totals")
    emit()
    cols = ["Metric"] + (["CPU (f90)"] if do_cpu else []) + (["GPU (CUDA C++)"] if do_gpu else [])
    emit("| " + " | ".join(cols) + " |")
    emit("|" + "|".join(["---"] * len(cols)) + "|")

    def line(label, cpu_cell, gpu_cell):
        parts = [label]
        if do_cpu:
            parts.append(cpu_cell)
        if do_gpu:
            parts.append(gpu_cell)
        emit("| " + " | ".join(parts) + " |")

    line("GeLB raw LOC", f"{sum_g_raw}", f"{sum_g_raw}")
    line("Backend raw LOC", f"{sum_c_raw}", f"{sum_p_raw}")
    exp_c_raw = _expansion(sum_g_raw, sum_c_raw)
    exp_p_raw = _expansion(sum_g_raw, sum_p_raw)
    line("Raw expansion",
         f"{_fmt_ratio(exp_c_raw)} ({_fmt_reduction(exp_c_raw)} shorter)",
         f"{_fmt_ratio(exp_p_raw)} ({_fmt_reduction(exp_p_raw)} shorter)")
    line("GeLB SLOC", f"{sum_g_sloc}", f"{sum_g_sloc}")
    line("Backend SLOC", f"{sum_c_sloc}", f"{sum_p_sloc}")
    exp_c_sloc = _expansion(sum_g_sloc, sum_c_sloc)
    exp_p_sloc = _expansion(sum_g_sloc, sum_p_sloc)
    line("SLOC expansion",
         f"{_fmt_ratio(exp_c_sloc)} ({_fmt_reduction(exp_c_sloc)} shorter)",
         f"{_fmt_ratio(exp_p_sloc)} ({_fmt_reduction(exp_p_sloc)} shorter)")
    emit()

    # ----- per-example averages -----
    emit("## Per-example averages")
    emit()
    cols = ["Metric"] + (["CPU (f90)"] if do_cpu else []) + (["GPU (CUDA C++)"] if do_gpu else [])
    emit("| " + " | ".join(cols) + " |")
    emit("|" + "|".join(["---"] * len(cols)) + "|")

    def ratios(sel_g, sel_o):
        out = []
        for r in rows:
            g = sel_g(r)
            o = sel_o(r)
            if g > 0 and o > 0:
                out.append(o / g)
        return out

    selectors = {
        "raw": (lambda r: r.gelb_raw, lambda r: r.cpu_raw, lambda r: r.gpu_raw),
        "sloc": (lambda r: r.gelb_sloc, lambda r: r.cpu_sloc, lambda r: r.gpu_sloc),
    }
    for label, kind, agg_fn, agg_name in [
        ("Raw mean expansion", "raw", mean, "mean"),
        ("Raw median expansion", "raw", median, "median"),
        ("SLOC mean expansion", "sloc", mean, "mean"),
        ("SLOC median expansion", "sloc", median, "median"),
    ]:
        sel_g, sel_c, sel_p = selectors[kind]
        parts = [label]
        if do_cpu:
            rs = ratios(sel_g, sel_c)
            v = agg_fn(rs) if rs else None
            parts.append(f"{_fmt_ratio(v)} ({_fmt_reduction(v)} shorter)")
        if do_gpu:
            rs = ratios(sel_g, sel_p)
            v = agg_fn(rs) if rs else None
            parts.append(f"{_fmt_ratio(v)} ({_fmt_reduction(v)} shorter)")
        emit("| " + " | ".join(parts) + " |")
    emit()

    # ----- by category (size-weighted SLOC) -----
    emit("## By category (size-weighted SLOC expansion)")
    emit()
    headers = ["Category", "n", "GeLB SLOC"]
    if do_cpu:
        headers += ["CPU SLOC", "CPU/GeLB"]
    if do_gpu:
        headers += ["GPU SLOC", "GPU/GeLB"]
    emit("| " + " | ".join(headers) + " |")
    emit("|" + "|".join(["---"] * len(headers)) + "|")
    cats = {}
    for r in rows:
        cats.setdefault(r.category, []).append(r)
    order = [c for c in _CATEGORY_ORDER if c in cats]
    for cat in order:
        rs = cats[cat]
        g = sum(r.gelb_sloc for r in rs)
        c = sum(r.cpu_sloc for r in rs)
        p = sum(r.gpu_sloc for r in rs)
        parts = [cat, str(len(rs)), str(g)]
        if do_cpu:
            parts += [str(c), _fmt_ratio(_expansion(g, c))]
        if do_gpu:
            parts += [str(p), _fmt_ratio(_expansion(g, p))]
        emit("| " + " | ".join(parts) + " |")
    emit()

    # ----- outliers -----
    emit("## Outliers (SLOC expansion)")
    emit()
    if do_cpu:
        usable = [r for r in rows if r.gelb_sloc > 0 and r.cpu_sloc > 0]
        by_cpu = sorted(usable, key=lambda r: r.cpu_sloc / r.gelb_sloc)
        lo, hi = by_cpu[0], by_cpu[-1]
        emit(f"* Tightest CPU ratio: `{lo.path}` — "
             f"{lo.cpu_sloc} / {lo.gelb_sloc} = "
             f"{lo.cpu_sloc / lo.gelb_sloc:.2f}\u00d7")
        emit(f"* Widest CPU ratio:   `{hi.path}` — "
             f"{hi.cpu_sloc} / {hi.gelb_sloc} = "
             f"{hi.cpu_sloc / hi.gelb_sloc:.2f}\u00d7")
    if do_gpu:
        usable = [r for r in rows if r.gelb_sloc > 0 and r.gpu_sloc > 0]
        by_gpu = sorted(usable, key=lambda r: r.gpu_sloc / r.gelb_sloc)
        lo, hi = by_gpu[0], by_gpu[-1]
        emit(f"* Tightest GPU ratio: `{lo.path}` — "
             f"{lo.gpu_sloc} / {lo.gelb_sloc} = "
             f"{lo.gpu_sloc / lo.gelb_sloc:.2f}\u00d7")
        emit(f"* Widest GPU ratio:   `{hi.path}` — "
             f"{hi.gpu_sloc} / {hi.gelb_sloc} = "
             f"{hi.gpu_sloc / hi.gelb_sloc:.2f}\u00d7")
    emit()


def write_tsv(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("example\tcategory\tgelb_raw\tgelb_sloc\t"
                "cpu_raw\tcpu_sloc\tgpu_raw\tgpu_sloc\n")
        for r in rows:
            f.write(f"{r.path}\t{r.category}\t"
                    f"{r.gelb_raw}\t{r.gelb_sloc}\t"
                    f"{r.cpu_raw}\t{r.cpu_sloc}\t"
                    f"{r.gpu_raw}\t{r.gpu_sloc}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure LOC savings of GeLB vs generated backend code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--examples", default="examples",
        help="directory to scan for *.gelb files (default: examples)",
    )
    parser.add_argument(
        "--backend", default="both", choices=["cpu", "gpu", "both"],
        help="which backend(s) to measure (default: both)",
    )
    parser.add_argument(
        "--tsv", default=None,
        help="dump per-file raw data to this TSV path",
    )
    parser.add_argument(
        "--num-timesteps", default="100",
        help="value passed to gelbc --num-timesteps (default: 100)",
    )
    parser.add_argument(
        "--exclude", action="append", default=[],
        help="path substring to exclude (may be repeated)",
    )
    args = parser.parse_args(argv)

    root = args.examples
    if not os.path.isabs(root):
        root = os.path.join(PROJECT_ROOT, root)
    if not os.path.isdir(root):
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    gelb_files = sorted(
        os.path.join(dp, fn)
        for dp, _, files in os.walk(root)
        for fn in files if fn.endswith(".gelb")
    )
    if args.exclude:
        gelb_files = [
            p for p in gelb_files
            if not any(sub in p for sub in args.exclude)
        ]
    if not gelb_files:
        print(f"no .gelb files under {root}", file=sys.stderr)
        return 1

    do_cpu = args.backend in ("cpu", "both")
    do_gpu = args.backend in ("gpu", "both")

    rows = []
    with tempfile.TemporaryDirectory(prefix="gelb_loc_") as tmp:
        for i, gelb in enumerate(gelb_files, start=1):
            rel = os.path.relpath(gelb, PROJECT_ROOT)
            print(f"[{i:2d}/{len(gelb_files)}] {rel}", file=sys.stderr)
            g_raw, g_sloc = count_loc_gelb(gelb)
            cat = categorize(rel)

            base = os.path.splitext(os.path.basename(gelb))[0]
            c_raw = c_sloc = p_raw = p_sloc = 0
            if do_cpu:
                out = os.path.join(tmp, f"{base}.f90")
                if compile_example(gelb, "cpu", out, args.num_timesteps):
                    c_raw, c_sloc = count_loc_fortran(out)
                else:
                    print(f"  ! CPU compile failed", file=sys.stderr)
            if do_gpu:
                out = os.path.join(tmp, f"{base}.cu")
                if compile_example(gelb, "gpu", out, args.num_timesteps):
                    # CUDA C++ comments are // and /* */, as in GeLB.
                    p_raw, p_sloc = count_loc_gelb(out)
                else:
                    print(f"  ! GPU compile failed", file=sys.stderr)

            rows.append(Row(rel, cat, g_raw, g_sloc, c_raw, c_sloc, p_raw, p_sloc))

    def compiled(r):
        if do_cpu and r.cpu_raw == 0:
            return False
        if do_gpu and r.gpu_raw == 0:
            return False
        return True

    usable = [r for r in rows if compiled(r)]
    dropped = len(rows) - len(usable)
    if dropped:
        print(f"warning: {dropped} example(s) dropped due to compile failures",
              file=sys.stderr)
    if not usable:
        print("error: no examples compiled successfully", file=sys.stderr)
        return 3

    if args.tsv:
        write_tsv(rows, args.tsv)
        print(f"wrote per-file TSV to {args.tsv}", file=sys.stderr)

    print_report(usable, do_cpu, do_gpu)
    return 0


if __name__ == "__main__":
    sys.exit(main())
