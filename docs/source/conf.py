import re
import sys
from importlib import metadata
from pathlib import Path
from types import ModuleType

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

# Importing ``avica`` normally eagerly imports the CLI and, through it, CASA
# and the complete pipeline.  Those optional runtime dependencies are not
# available on Read the Docs.  Register a lightweight package object so that
# autodoc can import individual modules without executing avica/__init__.py.
avica_package = ModuleType("avica")
avica_package.__path__ = [str(SOURCE_ROOT / "avica")]
avica_package.c = {
    "x": "", "g": "", "r": "", "b": "", "c": "", "w": "", "y": "",
}
sys.modules.setdefault("avica", avica_package)

autodoc_mock_imports = [
    "casampi", "casatools", "casatasks",
    "casacore", "fitsio", "matplotlib", "rich", "vasco", "vex",
    "pandas", "astropy", "numpy", "scipy",
    "sklearn", "polars", "google.protobuf",
    "typer", "avica.fitsidiutil._core", "_core",
]

project   = 'AVICA'
copyright = '2026, Avinash Kumar'
author    = 'Avinash Kumar'

pyproject = SOURCE_ROOT.parent / "pyproject.toml"
version_match = re.search(
    r'^version\s*=\s*"([^"]+)"', pyproject.read_text(), re.MULTILINE
)
release = version_match.group(1) if version_match else "unknown"
version = release

# ``avica.util`` displays the installed distribution version in its banner.
# The Read the Docs build imports directly from ``src`` rather than installing
# a wheel, so provide that one metadata value while autodoc imports modules.
_distribution_version = metadata.version


def _docs_distribution_version(distribution_name):
    if distribution_name.lower() == "avica":
        return release
    return _distribution_version(distribution_name)


metadata.version = _docs_distribution_version

extensions = [
    'sphinx.ext.napoleon',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'sphinx.ext.coverage',
    'sphinx.ext.autosectionlabel',
    'sphinxcontrib.asciinema',
]

autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'show-inheritance': True,
    'undoc-members': False,
}
autodoc_typehints = 'description'
autosummary_generate = True

# Napoleon
napoleon_google_docstring  = True
napoleon_numpy_docstring   = False
napoleon_use_param         = True
napoleon_use_rtype         = True
napoleon_preprocess_types  = True
napoleon_attr_annotations  = True

# Autosectionlabel
autosectionlabel_prefix_document = True
autosectionlabel_maxdepth = 1

# Intersphinx
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'numpy':  ('https://numpy.org/doc/stable', None),
    'astropy': ('https://docs.astropy.org/en/stable', None),
}

templates_path   = ['_templates']
exclude_patterns = []

html_theme       = 'sphinx_book_theme'
html_static_path = ['_static']
html_theme_options = {
    "home_page_in_toc":    True,
    "show_navbar_depth":   4,
    "show_toc_level":      3,
    "collapse_navigation": True,
}
