"""Sphinx configuration for the GeLB manuals.

Builds two "books" from this Sphinx project:

    usrman.rst   →  GeLB User Tutorial (docs/user/)
    devman.rst   →  GeLB Developer Manual (docs/dev/)

Both are reachable from `index.rst` and use this config. The site
eventually lives on ReadTheDocs (`gelb.readthedocs.io`); the
`.readthedocs.yaml` at the repo root consumes this file unchanged.

Local build:
    uv pip install -e '.[docs]'
    cd docs && make html
    open _build/html/index.html
"""

from __future__ import annotations

import pathlib
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

# Local Sphinx extensions / lexers live under docs/_ext/.
sys.path.insert(0, str(pathlib.Path(__file__).parent / "_ext"))

from gelb_lexer import GelbLexer  # noqa: E402  (sys.path just tweaked above)
from sphinx.highlighting import lexers  # noqa: E402

# Register the GeLB lexer so `.. code-block:: gelb` in the chapters
# syntax-highlights correctly instead of warning "Pygments lexer name
# 'gelb' is not known".
lexers["gelb"] = GelbLexer(startinline=True)

# -- Project metadata --------------------------------------------------

# Pull the version string from the installed gelb package rather than
# hard-coding it here; keeps the version on the cover consistent with
# whatever `pip show gelb` reports. `try/except` because the Sphinx
# build on ReadTheDocs installs the package before running us, but a
# local run without the package installed should still succeed (we'd
# just miss the version string).
try:
    _version = _pkg_version("gelb")
except PackageNotFoundError:
    _version = "unknown"

project = "GeLB"
copyright = "2007-%Y, Dragos-Bogdan Chirila"
author = "Dragos-Bogdan Chirila"
release = _version
version = ".".join(_version.split(".")[:2])  # short X.Y form

# -- General configuration ---------------------------------------------

extensions = [
    # LaTeX math rendering in the browser (via MathJax).
    "sphinx.ext.mathjax",
    # Link to Python / NumPy / matplotlib / SciPy docs via :py:obj:...
    # refs (optional but cheap to have registered).
    "sphinx.ext.intersphinx",
    # Auto-label every section so :ref:`Section Title` works without
    # manually placing a `.. _label:` before each heading.
    "sphinx.ext.autosectionlabel",
    # Copy-to-clipboard button on every code block.
    "sphinx_copybutton",
]

templates_path = ["_templates"]

# Exclude anything that isn't part of the user manual. The
# repo-root README / CHANGELOG / etc. live outside the Sphinx tree.
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "LANGUAGE_DESIGN.md",
    "visualizations/**",
]

# The default master document is `index`, which is what we have.
master_doc = "index"

# RST source files only.
source_suffix = {".rst": "restructuredtext"}

# Warn only, don't fail, on references that can't be resolved — the
# chapters currently contain a handful of :doc:`...` pointers whose
# targets may still be in progress. Flip to "fail" once the manual
# is stable.
nitpicky = False

# Categories of warnings that are NOT actionable issues in this
# project and would otherwise make `make html-strict` noisy:
#
#   autosectionlabel.*     — a handful of chapters use repeated
#     subsection titles like "Validation rules" / "Key methods" at
#     multiple levels within a single file. Keeping the headings
#     user-readable beats fragmenting them for the sake of unique
#     `:ref:` targets — cross-chapter references use `:doc:` anyway.
#
#   ref.citation           — `docs/user/18_further_reading.rst` is a
#     bibliography page: it lists references the reader should
#     consult, not citations woven into running text. Sphinx still
#     warns because no page inlines `[Name]_` against them; suppress.
suppress_warnings = [
    "autosectionlabel.*",
    "ref.citation",
]


# -- Custom :source: role ---------------------------------------------

# The manual can reference repo source files using
# `:source:`path/to/file.py`` — for example, pointing at
# `gelb/midware/program_analysis.py`. That role isn't a built-in in
# Sphinx, so define it here: turn the text into a hyperlink to the
# corresponding blob on GitHub's `main` branch. While the repo is
# still private the link 404s gracefully; once public it resolves.
def _setup_source_role(repo_url: str, branch: str):
    from docutils import nodes
    from docutils.parsers.rst import roles

    def _source_role(name, rawtext, text, lineno, inliner,
                     options=None, content=None):
        options = options or {}
        ref = f"{repo_url}/blob/{branch}/{text}"
        node = nodes.reference(rawtext, text, refuri=ref,
                               classes=["source-ref"], **options)
        return [node], []

    roles.register_local_role("source", _source_role)


_setup_source_role("https://github.com/dchirila/gelb", "main")

# Section anchoring: the chapters all start at H1 so each page has a
# unique title, and autosectionlabel scopes its generated labels per
# document (prevents collisions across chapters that happen to share
# a subsection name).
autosectionlabel_prefix_document = True
autosectionlabel_maxdepth = 3

# -- HTML output -------------------------------------------------------

# `furo` is the chosen theme — clean, modern, dark-mode native, math-
# friendly, and doesn't demand the kind of left-rail sidebar config
# that pydata_sphinx_theme or sphinx_rtd_theme need. To switch to the
# classic ReadTheDocs look, replace this with "sphinx_rtd_theme" and
# update docs/requirements.txt accordingly.
html_theme = "furo"
html_title = f"GeLB {version}"

html_theme_options = {
    # Accent colour: the amber that the website and the VSCode
    # extension both use.
    "light_css_variables": {
        "color-brand-primary":  "#d97706",
        "color-brand-content":  "#d97706",
    },
    "dark_css_variables": {
        "color-brand-primary":  "#fbbf24",
        "color-brand-content":  "#fbbf24",
    },
    # Edit-on-GitHub links on every page (activates once the repo is
    # public; harmless until then — it just produces a button pointing
    # at a 404).
    "source_repository": "https://github.com/dchirila/gelb/",
    "source_branch": "main",
    "source_directory": "docs/",
}

html_logo  = "figs/gelb_logo.svg"
html_favicon = None   # TODO: add a favicon before launch

html_static_path = ["_static"]

# If docs/_static/ doesn't exist yet, Sphinx warns. Create it lazily
# so we don't ship an empty directory into the repo.
_static = pathlib.Path(__file__).parent / "_static"
_static.mkdir(exist_ok=True)
# Same for _templates.
(pathlib.Path(__file__).parent / "_templates").mkdir(exist_ok=True)

# -- Intersphinx -------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3",       None),
    "numpy":  ("https://numpy.org/doc/stable/",   None),
    "scipy":  ("https://docs.scipy.org/doc/scipy/", None),
    "matplotlib": ("https://matplotlib.org/stable/", None),
}
intersphinx_disabled_reftypes = ["*"]   # opt-in per reference

# -- Pygments / syntax highlighting -----------------------------------

pygments_style = "friendly"
pygments_dark_style = "monokai"   # furo-specific

# Default language for unannotated `.. code-block::` directives. The
# chapters annotate most blocks explicitly; the few that don't are
# usually GeLB syntax, which has no Pygments lexer, so `text` gives a
# readable fallback.
highlight_language = "text"

# -- Copybutton --------------------------------------------------------

# Strip the leading `$ ` / `>>> ` / `# ` on copy so users can paste a
# command right into their shell without a cleanup step.
copybutton_prompt_text = r">>> |\.\.\. |\$ |# |\[\d+\]: "
copybutton_prompt_is_regexp = True

# -- LaTeX / PDF output ------------------------------------------------

# Two PDFs from ``make latexpdf``: the user tutorial and the
# developer manual, each rooted at its own ``*.rst`` so that each PDF
# contains exactly its chapters.  The tuple is ``(source_start_file,
# target_filename, title, author, doctype)``; the ``manual`` doctype
# produces a chapter-level structure (vs ``howto``'s section-level).
latex_documents = [
    ("usrman", "gelb-usrman.tex",
     "GeLB User Tutorial", author, "manual"),
    ("devman", "gelb-devman.tex",
     "GeLB Developer Manual", author, "manual"),
]

# Engine: ``xelatex``.  The chapters use Unicode characters (≥, →,
# Δ, etc.) that the default ``pdflatex`` engine can't render — it
# would fail with "Unicode character not set up for use with LaTeX".
# XeLaTeX handles Unicode natively.  Provided by ``texlive-xetex`` on
# Debian/Ubuntu (already in the recommended apt set documented for
# the PDF build).
latex_engine = "xelatex"

# Modest customisation: A4 paper.  Everything else inherits Sphinx
# defaults so the rendering tracks the upstream theme.
latex_elements = {
    "papersize": "a4paper",
    "pointsize": "10pt",
}

# -- ReadTheDocs quirks ------------------------------------------------

# When building on RTD the builder strips `\\n` inside conf.py's
# `html_context.display_...` flags, so we leave the extra bookkeeping
# off by default and let RTD inject its own context.
