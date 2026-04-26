#!/bin/bash
# Render Asymptote figures in docs/figs/ into vector PDF (for the
# paper) and vector SVG (for gelb-lang.org and the reference manual).
#
# Asymptote's raster-supersampling path (settings.render > 0) fails
# on macOS TeXLive because the bundled Asymptote can't invoke
# Ghostscript correctly. The .asy sources pin `settings.render = 0`,
# so they emit pure-vector EPS directly; this script finishes the
# pipeline:
#
#     .asy  --[asy]-->  .eps  --[gs]-->  .pdf  --[pdftocairo]-->  .svg
#
# Tools required:
#   - asy      (Homebrew: `brew install asymptote` -- NOT the
#              TeXLive-bundled asy, which has the gs-invocation bug
#              on macOS Tahoe)
#   - gs       (Homebrew: `brew install ghostscript`)
#   - pdftocairo  (Homebrew: `brew install poppler`)
#
# Usage: scripts/render_figs.sh  [name-without-extension ...]
# With no args, renders every *.asy in docs/figs/.

set -e
set -u

cd "$(dirname "$0")/../docs/figs"

# Locate the Homebrew asy on macOS; fall back to whichever asy is
# on PATH for Linux.
if [[ -x /opt/homebrew/bin/asy ]]; then
    ASY=/opt/homebrew/bin/asy
else
    ASY="$(command -v asy || true)"
fi
if [[ -z "${ASY}" ]]; then
    echo "error: asy not found. Install with 'brew install asymptote' on macOS" >&2
    echo "       or 'apt install asymptote' on Linux." >&2
    exit 1
fi

if ! command -v gs > /dev/null; then
    echo "error: gs (Ghostscript) not found." >&2
    exit 1
fi
if ! command -v pdftocairo > /dev/null; then
    echo "error: pdftocairo (from poppler) not found." >&2
    exit 1
fi

if [[ $# -eq 0 ]]; then
    TARGETS=(*.asy)
else
    TARGETS=("$@")
fi

for src in "${TARGETS[@]}"; do
    stem="${src%.asy}"
    echo "-> ${stem}"
    rm -f "${stem}.eps" "${stem}.pdf" "${stem}.svg"
    "${ASY}" "${stem}.asy"
    # -dEPSCrop is essential: without it, gs wraps the EPS in a
    # full US-Letter page, producing a 612x792 SVG with the figure
    # floating in the upper-left corner. With it, the PDF inherits
    # the EPS bounding box and the downstream SVG is the expected
    # tight-cropped figure.
    gs -dNOPAUSE -dBATCH -dQUIET -dEPSCrop -sDEVICE=pdfwrite \
       -sOutputFile="${stem}.pdf" "${stem}.eps"
    pdftocairo -svg "${stem}.pdf" "${stem}.svg"
    ls -lh "${stem}.eps" "${stem}.pdf" "${stem}.svg"
done

echo "Done. Paper-quality PDFs and web SVGs are in docs/figs/."
