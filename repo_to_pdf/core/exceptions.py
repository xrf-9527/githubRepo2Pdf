"""
Custom exceptions for repo-to-pdf.

This module defines a hierarchy of exceptions for better error handling
and debugging throughout the application.
"""

from typing import Optional


class RepoPDFError(Exception):
    """
    Base exception for all repo-to-pdf errors.

    All custom exceptions in this package inherit from this class,
    allowing for easy catching of all package-specific errors.

    Args:
        message: The error message
        details: Additional error details (optional)

    Example:
        >>> try:
        ...     raise RepoPDFError("Something went wrong")
        ... except RepoPDFError as e:
        ...     logger.error(f"Error: {e}")
    """

    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}\nDetails: {self.details}"
        return self.message


class ConfigurationError(RepoPDFError):
    """
    Raised when there's an error in configuration.

    This includes:
    - Invalid YAML syntax
    - Missing required configuration fields
    - Invalid configuration values
    - Type mismatches

    Example:
        >>> raise ConfigurationError(
        ...     "Invalid font size",
        ...     "fontsize must be one of: 7pt, 8pt, 9pt, 10pt, 11pt, 12pt"
        ... )
    """

    pass


class GitOperationError(RepoPDFError):
    """
    Raised when a Git operation fails.

    This includes:
    - Clone failures
    - Pull/fetch failures
    - Invalid repository URLs
    - Network errors
    - Authentication errors

    Example:
        >>> raise GitOperationError(
        ...     "Failed to clone repository",
        ...     "Repository not found: https://github.com/user/repo.git"
        ... )
    """

    pass


class ConversionError(RepoPDFError):
    """
    Raised when PDF conversion fails.

    This includes:
    - Pandoc execution errors
    - LaTeX compilation errors
    - Invalid Markdown syntax
    - Template errors

    Example:
        >>> raise ConversionError(
        ...     "Pandoc conversion failed",
        ...     "LaTeX Error: Undefined control sequence"
        ... )
    """

    pass


class ImageProcessingError(RepoPDFError):
    """
    Raised when image processing fails.

    This includes:
    - SVG to PNG conversion errors
    - Remote image download failures
    - Invalid image formats
    - Image file not found

    Example:
        >>> raise ImageProcessingError(
        ...     "Failed to convert SVG",
        ...     "Invalid SVG content: missing width and height"
        ... )
    """

    pass


class FileProcessingError(RepoPDFError):
    """
    Raised when file processing fails.

    This includes:
    - File read errors
    - Encoding errors
    - Permission errors
    - File not found errors

    Example:
        >>> raise FileProcessingError(
        ...     "Cannot read file",
        ...     "Permission denied: /path/to/file"
        ... )
    """

    pass


class EmojiProcessingError(RepoPDFError):
    """
    Raised when emoji processing fails.

    This includes:
    - Emoji download failures
    - PNG conversion errors
    - Invalid emoji sequences

    Example:
        >>> raise EmojiProcessingError(
        ...     "Failed to download emoji",
        ...     "Twemoji CDN unavailable for sequence: 1f600"
        ... )
    """

    pass


class TemplateError(RepoPDFError):
    """
    Raised when template processing fails.

    This includes:
    - Template file not found
    - Invalid template syntax
    - Missing template variables

    Example:
        >>> raise TemplateError(
        ...     "Template not found",
        ...     "No template file: templates/custom.yaml"
        ... )
    """

    pass


class ValidationError(RepoPDFError):
    """
    Raised when data validation fails.

    This includes:
    - Invalid file paths
    - Invalid URL formats
    - Out of range values
    - Type validation errors

    Example:
        >>> raise ValidationError(
        ...     "Invalid file path",
        ...     "Path traversal detected: ../../etc/passwd"
        ... )
    """

    pass
