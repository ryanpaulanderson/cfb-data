"""Configure the Sphinx documentation build."""

from importlib.metadata import version as package_version

project = "cfb-data"
author = "Ryan Anderson"
copyright = "2026, Ryan Anderson"
release = package_version("cfb-data")
version = release

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
]

source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}
root_doc = "index"
exclude_patterns = [
    "_build",
    "README.md",
    "history/**",
    "next-api-groups.md",
]

html_theme = "furo"
html_title = f"cfb-data {release} documentation"
html_theme_options = {
    "source_repository": "https://github.com/ryanpaulanderson/cfb-data/",
    "source_branch": "main",
    "source_directory": "docs/",
}

autodoc_class_signature = "separated"
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_typehints_format = "short"
python_use_unqualified_type_names = True

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
]
