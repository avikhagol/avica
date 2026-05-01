import os
import sys

sys.path.insert(0, os.path.abspath("../../src"))

autodoc_mock_imports = [
    "casampi", "casatools", "casatasks",
    "pandas", "astropy", "numpy", "scipy",
    "scikit-learn", "polars", "protobuf",
    "typer", "avica.fitsidiutil._core", "_core",
]

project   = 'avica'
copyright = '2026, Avinash Kumar'
author    = 'Avinash Kumar'
release   = '0.3.1'

extensions = [
    'sphinx.ext.napoleon',
    'sphinx.ext.autodoc',
    'sphinx.ext.intersphinx',
    'sphinx.ext.coverage',
    'sphinx.ext.autosectionlabel',
    'jupyter_sphinx',
    'sphinxcontrib.asciinema',
]

# Napoleon
napoleon_google_docstring  = True
napoleon_numpy_docstring   = False
napoleon_use_param         = True
napoleon_use_rtype         = True
napoleon_preprocess_types  = True
napoleon_attr_annotations  = True

# Autosectionlabel
autosectionlabel_prefix_document = True

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
