#!/usr/bin/env python3
"""Shared Sphinx-to-PDF builder for the GeLB manual."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


@dataclass(frozen=True)
class ManualPdfConfig:
    project_name: str
    master_doc: str
    main_document: str
    tex_filename: str
    pdf_filename: str
    image_dirs: tuple[str, ...] = (
        "user/figures", "figs", "images", "_static")
    xelatex_install_hint: str = (
        "Install a TeX distribution with XeLaTeX support.")


def generate_sphinx_config(config: ManualPdfConfig) -> str:
    """Generate the temporary Sphinx configuration."""
    return f'''# Minimal Sphinx configuration for PDF generation
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "_ext"))

from gelb_lexer import GelbLexer  # noqa: E402
from sphinx.highlighting import lexers  # noqa: E402

lexers["gelb"] = GelbLexer(startinline=True)

# Project information
project = {config.project_name!r}
copyright = '2007-%Y, Dragos-Bogdan Chirila'
author = 'Dragos-Bogdan Chirila'
release = '1.0'

# General configuration
extensions = []
templates_path = []
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The master toctree document
master_doc = {config.master_doc!r}

# Language
language = 'en'

def _setup_source_role(repo_url, branch):
    from docutils import nodes
    from docutils.parsers.rst import roles

    def _source_role(name, rawtext, text, lineno, inliner,
                     options=None, content=None):
        options = options or {{}}
        ref = f"{{repo_url}}/blob/{{branch}}/{{text}}"
        node = nodes.reference(rawtext, text, refuri=ref,
                               classes=["source-ref"], **options)
        return [node], []

    roles.register_local_role("source", _source_role)


_setup_source_role("https://github.com/dchirila/gelb", "main")

# LaTeX configuration for PDF output
latex_engine = 'xelatex'  # Enable Unicode support

latex_elements = {{
    'papersize': 'letterpaper',
    'pointsize': '10pt',
    'classoptions': ',oneside',  # No blank verso pages
    'preamble': r"""\\usepackage{{fontspec}}
\\IfFontExistsTF{{Times New Roman}}{{\\setmainfont{{Times New Roman}}}}{{\\setmainfont{{TeX Gyre Termes}}}}
\\IfFontExistsTF{{Helvetica Neue}}{{\\setsansfont{{Helvetica Neue}}}}{{\\setsansfont{{TeX Gyre Heros}}}}
\\IfFontExistsTF{{Menlo}}{{\\setmonofont{{Menlo}}}}{{\\setmonofont{{DejaVu Sans Mono}}}}
\\usepackage{{fancyhdr}}
\\pagestyle{{fancy}}
\\fancyhf{{}}
\\fancyhead[L]{{\\leftmark}}
\\fancyhead[R]{{\\thepage}}
\\renewcommand{{\\headrulewidth}}{{0.4pt}}
\\usepackage{{hyperref}}
\\hypersetup{{
    colorlinks=true,
    linkcolor=blue,
    filecolor=magenta,
    urlcolor=cyan,
}}
""",
    'fncychap': r'\\usepackage[Sonny]{{fncychap}}',
    'printindex': '',
}}

# Grouping the document tree into LaTeX files
latex_documents = [
    (master_doc, {config.tex_filename!r}, {config.project_name!r},
     'Dragos-Bogdan Chirila', 'manual'),
]

suppress_warnings = []
'''


def setup_sphinx_build(
        docs_dir: Path, build_dir: Path, config: ManualPdfConfig) -> None:
    """Set up Sphinx inputs in the temporary build directory."""
    conf_path = build_dir / "conf.py"
    conf_path.write_text(generate_sphinx_config(config))

    for rst_file in docs_dir.rglob("*.rst"):
        relative_path = rst_file.relative_to(docs_dir)
        dest_path = build_dir / relative_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rst_file, dest_path)

    ext_dir = docs_dir / "_ext"
    if ext_dir.exists():
        shutil.copytree(ext_dir, build_dir / "_ext", dirs_exist_ok=True)

    for image_dir in config.image_dirs:
        src_img_dir = docs_dir / image_dir
        if src_img_dir.exists():
            dest_img_dir = build_dir / image_dir
            shutil.copytree(src_img_dir, dest_img_dir, dirs_exist_ok=True)


def _copy_latex_assets(
        build_dir: Path, latex_dir: Path, config: ManualPdfConfig) -> None:
    for image_dir in config.image_dirs:
        src_img_dir = build_dir / image_dir
        if src_img_dir.exists():
            dest_img_dir = latex_dir / image_dir
            shutil.copytree(src_img_dir, dest_img_dir, dirs_exist_ok=True)


def build_pdf_with_sphinx(
        build_dir: Path, output_pdf: Path, config: ManualPdfConfig) -> bool:
    """Build a PDF from the prepared temporary Sphinx tree."""
    print("Building LaTeX files with Sphinx...")
    latex_dir = build_dir / "_build" / "latex"

    result = subprocess.run([
        sys.executable, "-m", "sphinx",
        "-b", "latex",
        "-q",
        "-W", "--keep-going",
        str(build_dir),
        str(latex_dir),
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Sphinx build warnings/errors:\n{result.stderr}")

    _copy_latex_assets(build_dir, latex_dir, config)

    print("Building PDF from LaTeX (this may take a moment)...")

    tex_file = config.tex_filename
    if not (latex_dir / tex_file).exists():
        raise FileNotFoundError(f"LaTeX file {tex_file} not found!")

    result = subprocess.run([
        "latexmk",
        "-xelatex",
        "-quiet",
        "-pdf",
        tex_file,
    ], cwd=latex_dir, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"LaTeX compilation errors:\n{result.stderr}")
        print("Trying direct xelatex compilation...")
        for _ in range(3):
            subprocess.run(
                ["xelatex", "-interaction=nonstopmode", tex_file],
                cwd=latex_dir,
                capture_output=True)

    pdf_path = latex_dir / config.pdf_filename
    if pdf_path.exists():
        shutil.copy2(pdf_path, output_pdf)
        return True

    return False


def build_manual(config: ManualPdfConfig) -> int:
    """Main build workflow for a configured manual."""
    project_root = Path(__file__).parent.parent
    docs_dir = project_root / "docs"
    output_pdf = project_root / config.pdf_filename

    if not docs_dir.exists():
        print(f"Error: Documentation directory not found: {docs_dir}")
        return 1

    main_rst = docs_dir / config.main_document
    if not main_rst.exists():
        print(f"Error: Main document not found: {main_rst}")
        return 1

    with tempfile.TemporaryDirectory() as temp_dir:
        build_dir = Path(temp_dir)

        try:
            print("Setting up Sphinx build environment...")
            setup_sphinx_build(docs_dir, build_dir, config)

            print("Building PDF with Sphinx...")
            if build_pdf_with_sphinx(build_dir, output_pdf, config):
                print(f"\nPDF created successfully: {output_pdf}")
                size_mb = output_pdf.stat().st_size / (1024 * 1024)
                print(f"  File size: {size_mb:.1f} MB")
                return 0

            print("\nFailed to build PDF")
            return 1
        except Exception as exc:
            print(f"\nError during PDF build: {exc}")
            import traceback
            traceback.print_exc()
            return 1


def check_dependencies(config: ManualPdfConfig) -> int:
    """Check external tools before starting the build."""
    try:
        subprocess.run(["sphinx-build", "--version"],
                       capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: Sphinx is not installed or not in PATH")
        print("Install with: pip install sphinx")
        return 1

    try:
        subprocess.run(["latexmk", "--version"],
                       capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Warning: latexmk not found, will try direct xelatex")
        try:
            subprocess.run(["xelatex", "--version"],
                           capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Error: XeLaTeX is not installed")
            print(config.xelatex_install_hint)
            return 1

    return 0


def checked_main(config: ManualPdfConfig) -> None:
    dep_status = check_dependencies(config)
    if dep_status:
        sys.exit(dep_status)
    sys.exit(build_manual(config))
