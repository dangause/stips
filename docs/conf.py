"""Sphinx configuration for the STIPS documentation site.

MyST markdown pages, the furo theme, autodoc for the Python API, and the local
``stips_cli`` extension that renders the CLI reference from the click command
tree at build time.
"""

import os
import re
import sys
from pathlib import Path

DOCS = Path(__file__).parent
sys.path.insert(0, str(DOCS / "_ext"))

project = "STIPS"
author = "Daniel Gause and Kyle B. Westfall"
copyright = "2026, the STIPS authors"
# The release number lives in CITATION.cff, which every release updates.
release = re.search(
    r"^version:\s*(\S+)", (DOCS.parent / "CITATION.cff").read_text(), re.M
).group(1)
version = ".".join(release.split(".")[:2])

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx_autodoc_typehints",
    "sphinxcontrib.mermaid",
    "stips_cli",
]

source_suffix = {".md": "markdown"}
# docs/ also holds internal working notes (audits, plans, poster drafts, one-off
# findings) and the gitignored diagrams/. They stay in the repo, unpublished.
exclude_patterns = [
    "_build",
    "README.md",
    "audit",
    "plans",
    "superpowers",
    "diagrams",
    "aas246-*",
    "poster-*",
    "methods-handout.*",
    "ctio-amp-a01-finding.md",
    "calibration_metrics_assessment.md",
    "logging-improvements.md",
    "pipeline-brittleness-and-modernization.md",
]

# MyST
myst_enable_extensions = ["colon_fence", "deflist", "fieldlist"]
myst_heading_anchors = 3
# The guides use ```mermaid fences, which GitHub also renders.
myst_fence_as_directive = ["mermaid"]
# The diagrams set light node fills, so keep Mermaid's light theme in dark mode
# too; _static/custom.css puts them on a light panel there.
mermaid_dark_theme = "default"

# autodoc
autodoc_member_order = "bysource"
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_typehints = "description"
always_document_param_types = True
napoleon_google_docstring = True
napoleon_numpy_docstring = False
# Render "Attributes:" sections as fields of the class: as separate attribute
# entries they collide with the dataclass fields autodoc already documents.
napoleon_use_ivar = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "astropy": ("https://docs.astropy.org/en/stable/", None),
}

# sphinx-copybutton: strip shell prompts and Python REPL prompts when copying.
copybutton_prompt_text = r">>> |\.\.\. |\$ "
copybutton_prompt_is_regexp = True

html_theme = "furo"
html_title = f"STIPS {release}"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "source_repository": "https://github.com/dangause/stips/",
    "source_branch": "dev",
    "source_directory": "docs/",
}
# Read the Docs sets the canonical URL per version (/en/latest/, /en/stable/, ...).
html_baseurl = os.environ.get("READTHEDOCS_CANONICAL_URL", "")
