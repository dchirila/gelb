# Minimal Sphinx makefile for GeLB.
#
# Usage (from the docs/ directory):
#     make html     # build the HTML site at _build/html/
#     make clean    # remove _build/
#     make linkcheck
#
# Requires: `pip install -e '.[docs]'` from the repo root.

SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile html-strict

# Strict build that fails on warnings — for CI and pre-release
# cleanup sweeps. The default `make html` tolerates warnings so that
# new chapters can be iterated on without triggering a red error on
# every small formatting issue in neighbouring chapters.
html-strict:
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" -W --keep-going $(O)

# Catch-all: route any target we haven't explicitly defined to
# sphinx-build's default handler.
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
