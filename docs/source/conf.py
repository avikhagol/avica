# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html



import os
import sys
# sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath("../../src"))
autodoc_mock_imports = [
    "casampi", "casatools", "casatasks",   "pandas",
  "scipy",  "scikit-learn",  "polars",  "protobuf==3.20.3",   "typer",]


package_path = os.path.abspath('../../src')
# os.environ['PYTHONPATH'] = ':'.join((package_path, os.environ.get('PYTHONPATH', '')))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'vasco'
copyright = '2026, Avinash Kumar'
author = 'Avinash Kumar'
release = '0.3.0.2'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ['sphinx.ext.napoleon',
    'sphinx.ext.autodoc',
    # 'sphinx.ext.viewcode',
    'sphinx.ext.coverage',
    'sphinx.ext.autosectionlabel',
    'jupyter_sphinx',
]

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_book_theme'
html_static_path = ['_static']
html_theme_options = {
    "home_page_in_toc": True,
    "show_navbar_depth": 4,
    "show_toc_level": 3,
    "collapse_navigation": True,
}
