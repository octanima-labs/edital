"""Sphinx configuration for Edital's source-docstring API reference."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

project = "edital"
author = "octanima-labs"
copyright = "2026, octanima-labs"
release = "0.3.0"
extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx.ext.napoleon", "sphinx_autodoc_typehints"]
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
root_doc = "index"
autodoc_class_signature = "mixed"
autodoc_member_order = "bysource"
autodoc_typehints = "description"
napoleon_google_docstring = True
myst_heading_anchors = 3
html_theme = "pydata_sphinx_theme"
html_title = "Edital documentation"
