"""
Constants and configuration defaults for repo-to-pdf.

This module centralizes all magic numbers, file size limits, timeouts,
and other configuration constants to avoid hardcoding values throughout
the codebase.
"""

from typing import Dict, Set

# ============================================================================
# File Size Limits
# ============================================================================

MAX_FILE_SIZE_MB: float = 0.5
"""Maximum file size in MB before a file is skipped"""

MAX_FILE_SIZE_BYTES: int = int(MAX_FILE_SIZE_MB * 1024 * 1024)
"""Maximum file size in bytes"""

MAX_LINES_BEFORE_SPLIT: int = 1000
"""Maximum number of lines before a file is split into parts"""

CHUNK_SIZE_LINES: int = 800
"""Number of lines per chunk when splitting large files"""

# ============================================================================
# Line and String Length Limits
# ============================================================================

MAX_LINE_LENGTH_DEFAULT: int = 80
"""Default maximum line length before wrapping"""

MAX_LINE_LENGTH_HARD: int = 200
"""Hard maximum line length (absolute threshold)"""

STRING_BREAK_LENGTH: int = 100
"""Minimum string length before breaking into multiple lines"""

WRAP_WIDTH_RATIO: float = 0.75
"""Ratio of max_line_length to use for wrapping width"""

# ============================================================================
# Network Timeouts
# ============================================================================

EMOJI_DOWNLOAD_TIMEOUT: int = 10
"""Timeout in seconds for emoji downloads"""

IMAGE_DOWNLOAD_TIMEOUT: int = 10
"""Timeout in seconds for remote image downloads"""

GIT_CLONE_TIMEOUT: int = 300
"""Timeout in seconds for git clone operations"""

NETWORK_RETRY_ATTEMPTS: int = 3
"""Number of retry attempts for network operations"""

NETWORK_RETRY_DELAY: float = 1.0
"""Delay in seconds between retry attempts"""

# ============================================================================
# Concurrency Settings
# ============================================================================

MAX_CONCURRENT_FILES: int = 4
"""Maximum number of files to process concurrently"""

MAX_CONCURRENT_DOWNLOADS: int = 5
"""Maximum number of concurrent image/emoji downloads"""

MAX_WORKER_THREADS: int = 8
"""Maximum number of worker threads for I/O operations"""

# ============================================================================
# Memory Management
# ============================================================================

STREAM_CHUNK_SIZE: int = 8192
"""Chunk size in bytes for streaming file operations"""

CACHE_MAX_SIZE: int = 128
"""Maximum size for LRU caches"""

MEMORY_LIMIT_MB: int = 500
"""Target memory limit in MB"""

# ============================================================================
# Image Processing Settings
# ============================================================================

DEFAULT_IMAGE_WIDTH: int = 800
"""Default width in pixels for images without dimensions"""

DEFAULT_IMAGE_HEIGHT: int = 600
"""Default height in pixels for images without dimensions"""

CAIROSVG_WIDTH: int = 1600
"""Parent width for CairoSVG conversion"""

CAIROSVG_HEIGHT: int = 1200
"""Parent height for CairoSVG conversion"""

CAIROSVG_SCALE: float = 2.0
"""Scale factor for CairoSVG conversion (higher = better quality)"""

# ============================================================================
# File Extensions
# ============================================================================

IMAGE_EXTENSIONS: Set[str] = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".svgz", ".webp"}
"""Supported image file extensions"""

BINARY_EXTENSIONS: Set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dylib",
    ".dll",
    ".class",
    ".o",
    ".obj",
    ".exe",
    ".bin",
}
"""Binary file extensions to ignore"""

CODE_EXTENSIONS: Dict[str, str] = {
    # Frontend
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vue": "javascript",
    ".svelte": "javascript",
    ".css": "css",
    ".scss": "css",
    ".sass": "css",
    ".less": "css",
    ".html": "html",
    ".htm": "html",
    ".json": "json",
    ".graphql": "graphql",
    ".gql": "graphql",
    # Backend
    ".py": "python",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".clj": "clojure",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    # Configuration and Scripts
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".fish": "fish",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".ini": "ini",
    ".conf": "conf",
    ".env": "bash",
    # Documentation
    ".md": "markdown",
    ".mdx": "mdx",
    ".rst": "rst",
    ".txt": "text",
    # Other
    ".dockerfile": "dockerfile",
    ".Dockerfile": "dockerfile",
    ".makefile": "makefile",
    ".Makefile": "makefile",
}
"""Mapping of file extensions to language identifiers for syntax highlighting"""

# ============================================================================
# Default Ignore Patterns
# ============================================================================

DEFAULT_IGNORE_PATTERNS: Set[str] = {
    # Dependencies
    "node_modules",
    "vendor",
    "bower_components",
    # Build outputs
    "dist",
    "build",
    "out",
    "target",
    ".next",
    ".nuxt",
    # Version control
    ".git",
    ".svn",
    ".hg",
    # Python
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".venv",
    "venv",
    ".tox",
    ".eggs",
    "*.egg-info",
    # IDE
    ".idea",
    ".vscode",
    "*.swp",
    "*.swo",
    ".project",
    ".settings",
    # OS
    ".DS_Store",
    "Thumbs.db",
    # Logs and temp
    "*.log",
    ".cache",
    ".temp",
    "tmp",
    # Lock files
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "Gemfile.lock",
    "poetry.lock",
    "Pipfile.lock",
}
"""Default patterns for files and directories to ignore"""

# ============================================================================
# PDF and LaTeX Settings
# ============================================================================

DEFAULT_MARGIN: str = "margin=1in"
"""Default page margin"""

DEFAULT_FONTSIZE: str = "10pt"
"""Default document font size"""

VALID_FONTSIZES: Set[str] = {"7pt", "8pt", "9pt", "10pt", "11pt", "12pt", "14pt"}
"""Valid font size options"""

CODE_FONTSIZE_OPTIONS: Dict[str, str] = {
    "tiny": r"\tiny",
    "scriptsize": r"\scriptsize",
    "footnotesize": r"\footnotesize",
    "small": r"\small",
    "normalsize": r"\normalsize",
}
"""LaTeX code font size commands"""

DEFAULT_CODE_FONTSIZE: str = r"\small"
"""Default code block font size"""

DEFAULT_LINESPREAD: str = "1.0"
"""Default line spacing"""

DEFAULT_PARSKIP: str = "6pt"
"""Default paragraph spacing"""

# ============================================================================
# Device Presets
# ============================================================================

DEVICE_PRESETS: Dict[str, Dict] = {
    "desktop": {
        "description": "桌面端阅读优化",
        "template": "default",
        "pdf_overrides": {
            "margin": "margin=1in",
            "fontsize": "10pt",
            "code_fontsize": r"\small",
            "linespread": "1.0",
        },
    },
    "kindle7": {
        "description": "7英寸Kindle设备优化",
        "template": "kindle",
        "pdf_overrides": {
            "margin": "margin=0.4in",
            "fontsize": "11pt",
            "code_fontsize": r"\small",
            "linespread": "1.0",
            "parskip": "5pt",
            "max_file_size": "200KB",
            "max_line_length": 60,
        },
    },
    "tablet": {
        "description": "平板设备阅读优化",
        "template": "technical",
        "pdf_overrides": {
            "margin": "margin=0.6in",
            "fontsize": "9pt",
            "code_fontsize": r"\small",
            "linespread": "0.95",
        },
    },
    "mobile": {
        "description": "手机端阅读优化",
        "template": "kindle",
        "pdf_overrides": {
            "margin": "margin=0.3in",
            "fontsize": "7pt",
            "code_fontsize": r"\tiny",
            "linespread": "0.85",
            "parskip": "2pt",
        },
    },
}
"""Device-specific preset configurations"""

# ============================================================================
# Emoji Settings
# ============================================================================

TWEMOJI_VERSIONS: list = ["v14.0.2", "v14.0.0", "master"]
"""Twemoji CDN versions to try, in order of preference"""

TWEMOJI_CDN_URL: str = (
    "https://raw.githubusercontent.com/twitter/twemoji/{version}/assets/svg/{name}.svg"
)
"""Twemoji CDN URL template"""

EMOJI_CACHE_DIR: str = "images/emoji"
"""Emoji cache directory relative to temp directory"""

# ============================================================================
# SVG Conversion Settings
# ============================================================================

SVG_DEFAULT_WIDTH: int = 800
"""Default SVG width in pixels if not specified"""

SVG_DEFAULT_HEIGHT: int = 600
"""Default SVG height in pixels if not specified"""

SVG_SCALE: float = 2.0
"""Scale factor for SVG to PNG conversion (higher = better quality)"""

SVG_OUTPUT_WIDTH: int = 1600
"""Output width for SVG to PNG conversion"""

SVG_OUTPUT_HEIGHT: int = 1200
"""Output height for SVG to PNG conversion"""

# ============================================================================
# Logging
# ============================================================================

LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
"""Default logging format"""

LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
"""Default logging date format"""

# ============================================================================
# Pandoc Settings
# ============================================================================

PANDOC_TOC_DEPTH: int = 2
"""Table of contents depth for pandoc"""

PANDOC_HIGHLIGHT_STYLE: str = "tango"  # Changed from monochrome for better readability
"""Default syntax highlighting style"""

PANDOC_PDF_ENGINE: str = "xelatex"
"""PDF engine to use with pandoc"""
