#!/usr/bin/env python3
"""
Build a PDF version of the GeLB Developer Manual using Sphinx.

This script sets up a minimal Sphinx configuration and builds the documentation
to PDF format with proper handling of includes and Unicode support.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def generate_sphinx_config():
    """Generate Sphinx configuration as a string."""
    return '''# Minimal Sphinx configuration for PDF generation
import os
import sys

# Project information
project = 'GeLB Developer Manual'
copyright = '2024, GeLB Development Team'
author = 'GeLB Development Team'
release = '1.0'

# General configuration
extensions = []
templates_path = []
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The master toctree document
master_doc = 'devman'

# Language
language = 'en'

# LaTeX configuration for PDF output
latex_engine = 'xelatex'  # Enable Unicode support

latex_elements = {
    'papersize': 'letterpaper',
    'pointsize': '10pt',
    'preamble': r"""\\usepackage{fontspec}
\\setmainfont{DejaVu Serif}
\\setsansfont{DejaVu Sans}
\\setmonofont{DejaVu Sans Mono}
\\usepackage{fancyhdr}
\\pagestyle{fancy}
\\fancyhf{}
\\fancyhead[L]{\\leftmark}
\\fancyhead[R]{\\thepage}
\\renewcommand{\\headrulewidth}{0.4pt}
\\usepackage{hyperref}
\\hypersetup{
    colorlinks=true,
    linkcolor=blue,
    filecolor=magenta,
    urlcolor=cyan,
}
""",
    'fncychap': r'\\usepackage[Bjornstrup]{fncychap}',
    'printindex': '',
}

# Grouping the document tree into LaTeX files
latex_documents = [
    (master_doc, 'GeLB_Developer_Manual.tex', 'GeLB Developer Manual',
     'GeLB Development Team', 'manual'),
]

# Disable some warnings
suppress_warnings = ['misc.highlighting_failure']
'''


def setup_sphinx_build(docs_dir, build_dir):
    """Set up Sphinx configuration in the build directory."""
    # Create conf.py
    conf_path = build_dir / 'conf.py'
    conf_path.write_text(generate_sphinx_config())
    
    # Copy all RST files maintaining directory structure
    for rst_file in docs_dir.rglob('*.rst'):
        relative_path = rst_file.relative_to(docs_dir)
        dest_path = build_dir / relative_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rst_file, dest_path)
    
    # Copy any image files if they exist
    for img_dir in ['figs', 'images', '_static']:
        src_img_dir = docs_dir / img_dir
        if src_img_dir.exists():
            dest_img_dir = build_dir / img_dir
            shutil.copytree(src_img_dir, dest_img_dir, dirs_exist_ok=True)


def build_pdf_with_sphinx(build_dir, output_pdf):
    """Build PDF using Sphinx and LaTeX."""
    # Build LaTeX files using Sphinx
    print("Building LaTeX files with Sphinx...")
    latex_dir = build_dir / '_build' / 'latex'
    
    result = subprocess.run([
        sys.executable, '-m', 'sphinx',
        '-b', 'latex',
        '-q',  # Quiet mode
        '-W', '--keep-going',  # Warnings as errors but continue
        str(build_dir),
        str(latex_dir)
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Sphinx build warnings/errors:\n{result.stderr}")
        # Continue anyway as warnings might not be critical
    
    # Build PDF from LaTeX
    print("Building PDF from LaTeX (this may take a moment)...")
    os.chdir(latex_dir)
    
    # Run latexmk to build PDF
    tex_file = 'GeLB_Developer_Manual.tex'
    if not Path(tex_file).exists():
        raise FileNotFoundError(f"LaTeX file {tex_file} not found!")
    
    # Use latexmk for automatic compilation with proper reruns
    result = subprocess.run([
        'latexmk',
        '-xelatex',  # Use XeLaTeX
        '-quiet',    # Less verbose output
        '-pdf',      # Generate PDF
        tex_file
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"LaTeX compilation errors:\n{result.stderr}")
        # Try direct xelatex as fallback
        print("Trying direct xelatex compilation...")
        for _ in range(3):  # Run multiple times for references
            subprocess.run(['xelatex', '-interaction=nonstopmode', tex_file], 
                         capture_output=True)
    
    # Copy PDF to final location
    pdf_path = latex_dir / 'GeLB_Developer_Manual.pdf'
    if pdf_path.exists():
        shutil.copy2(pdf_path, output_pdf)
        return True
    
    return False


def main():
    """Main function to orchestrate the PDF build process."""
    # Paths
    project_root = Path(__file__).parent.parent
    docs_dir = project_root / 'docs'
    output_pdf = project_root / 'GeLB_Developer_Manual.pdf'
    
    # Check that docs directory exists
    if not docs_dir.exists():
        print(f"Error: Documentation directory not found: {docs_dir}")
        sys.exit(1)
    
    # Check that main document exists
    devman_rst = docs_dir / 'devman.rst'
    if not devman_rst.exists():
        print(f"Error: Main document not found: {devman_rst}")
        sys.exit(1)
    
    # Create temporary build directory
    with tempfile.TemporaryDirectory() as temp_dir:
        build_dir = Path(temp_dir)
        
        try:
            # Set up Sphinx configuration and copy files
            print("Setting up Sphinx build environment...")
            setup_sphinx_build(docs_dir, build_dir)
            
            # Build PDF
            print("Building PDF with Sphinx...")
            if build_pdf_with_sphinx(build_dir, output_pdf):
                print(f"\n✓ PDF created successfully: {output_pdf}")
                
                # Get file size
                size_mb = output_pdf.stat().st_size / (1024 * 1024)
                print(f"  File size: {size_mb:.1f} MB")
            else:
                print("\n✗ Failed to build PDF")
                sys.exit(1)
                
        except Exception as e:
            print(f"\n✗ Error during PDF build: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    # Clean up any temporary merged files that might exist
    merged_rst = docs_dir / 'devman_merged.rst'
    if merged_rst.exists():
        merged_rst.unlink()
        print("  Cleaned up temporary files")


if __name__ == '__main__':
    # Check dependencies
    try:
        subprocess.run(['sphinx-build', '--version'], 
                      capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: Sphinx is not installed or not in PATH")
        print("Install with: pip install sphinx")
        sys.exit(1)
    
    try:
        subprocess.run(['latexmk', '--version'], 
                      capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Warning: latexmk not found, will try direct xelatex")
        try:
            subprocess.run(['xelatex', '--version'], 
                          capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Error: XeLaTeX is not installed")
            print("Install with: sudo apt-get install texlive-xetex")
            sys.exit(1)
    
    main()