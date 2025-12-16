"""
repo_to_pdf - GitHub Repository to PDF Converter
================================================

A modular, high-performance tool for converting GitHub repositories
into beautifully formatted PDF documents with syntax highlighting.

Main Components:
    - core: Configuration, constants, and exceptions
    - processors: File, Markdown, and code processing
    - converters: Image, Emoji, and LaTeX conversion
    - git: Repository management
    - stats: Statistics and directory tree generation
    - templates: Template engine for customization

Example:
    >>> from repo_to_pdf.core.config import AppConfig
    >>> from repo_to_pdf.converter import RepoPDFConverter
    >>>
    >>> config = AppConfig.from_yaml("config.yaml")
    >>> converter = RepoPDFConverter(config)
    >>> pdf_path = converter.convert()

Version: 2.0.0
Author: Repo-to-PDF Contributors
License: MIT
"""

__version__ = "2.0.0"
__author__ = "Repo-to-PDF Contributors"
__license__ = "MIT"

from repo_to_pdf.converter import RepoPDFConverter
from repo_to_pdf.core.config import AppConfig
from repo_to_pdf.core.exceptions import RepoPDFError

__all__ = [
    "AppConfig",
    "RepoPDFConverter",
    "RepoPDFError",
    "__version__",
]
