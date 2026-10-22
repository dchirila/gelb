#!/usr/bin/env python3
"""Build a PDF version of the GeLB Developer Manual using Sphinx."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from manual_pdf_builder import (  # noqa: E402
    ManualPdfConfig,
    build_manual,
    build_pdf_with_sphinx as _build_pdf_with_sphinx,
    checked_main,
    generate_sphinx_config as _generate_sphinx_config,
    setup_sphinx_build as _setup_sphinx_build,
)


CONFIG = ManualPdfConfig(
    project_name="GeLB Developer Manual",
    master_doc="devman",
    main_document="devman.rst",
    tex_filename="GeLB_Developer_Manual.tex",
    pdf_filename="GeLB_Developer_Manual.pdf",
    xelatex_install_hint="Install with: brew install --cask mactex",
)


def generate_sphinx_config():
    return _generate_sphinx_config(CONFIG)


def setup_sphinx_build(docs_dir, build_dir):
    return _setup_sphinx_build(Path(docs_dir), Path(build_dir), CONFIG)


def build_pdf_with_sphinx(build_dir, output_pdf):
    return _build_pdf_with_sphinx(
        Path(build_dir), Path(output_pdf), CONFIG)


def main():
    return build_manual(CONFIG)


if __name__ == "__main__":
    checked_main(CONFIG)
