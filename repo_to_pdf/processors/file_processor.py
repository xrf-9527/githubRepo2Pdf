"""
File processing module.

This module handles file reading, filtering, and validation with security
best practices and performance optimizations.
"""

import fnmatch
import logging
from pathlib import Path
from typing import Iterator, List, Optional

from repo_to_pdf.core.config import AppConfig
from repo_to_pdf.core.constants import (
    BINARY_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    STREAM_CHUNK_SIZE,
)
from repo_to_pdf.core.exceptions import FileProcessingError, ValidationError
from repo_to_pdf.core.path_matching import posix_glob_match_any

logger = logging.getLogger(__name__)


class FileProcessor:
    """
    Handles file operations with security and performance optimizations.

    This class provides methods for:
    - Safe file reading (with streaming support for large files)
    - File filtering based on ignore patterns
    - Path security validation (prevents path traversal)
    - File metadata collection

    Attributes:
        config: Application configuration
        ignore_patterns: Compiled list of ignore patterns

    Example:
        >>> config = AppConfig.from_yaml("config.yaml")
        >>> processor = FileProcessor(config)
        >>> files = processor.collect_files(repo_path)
        >>> for file_path in files:
        ...     content = processor.read_file_safe(file_path)
    """

    def __init__(self, config: AppConfig):
        """
        Initialize file processor.

        Args:
            config: Application configuration
        """
        self.config = config
        self.ignore_patterns = self._compile_ignore_patterns()

    def _compile_ignore_patterns(self) -> List[str]:
        """
        Compile ignore patterns from configuration.

        Returns:
            List of ignore patterns
        """
        patterns = self.config.ignores.copy() if self.config.ignores else []
        logger.debug(f"Compiled {len(patterns)} ignore patterns")
        return patterns

    def should_ignore(self, path: Path) -> bool:
        """
        Check if a file or directory should be ignored.

        Args:
            path: Path to check

        Returns:
            True if path should be ignored, False otherwise

        Example:
            >>> processor.should_ignore(Path("node_modules/package.json"))
            True
            >>> processor.should_ignore(Path("src/main.py"))
            False
        """
        path_str = str(path)
        path_name = path.name

        # Check exact matches
        for pattern in self.ignore_patterns:
            # Directory match
            if pattern in path_str:
                return True

            # File name match
            if path_name == pattern:
                return True

            # Wildcard match
            if "*" in pattern:
                if fnmatch.fnmatch(path_name, pattern):
                    return True
                if fnmatch.fnmatch(path_str, pattern):
                    return True

        # Ignore binary files
        if path.suffix in BINARY_EXTENSIONS:
            return True

        return False

    def is_safe_path(self, base_dir: Path, target_path: Path) -> bool:
        """
        Validate that target path is within base directory.

        This prevents path traversal attacks (e.g., ../../../etc/passwd).

        Args:
            base_dir: Base directory that should contain the target
            target_path: Path to validate

        Returns:
            True if path is safe, False otherwise

        Example:
            >>> base = Path("/home/user/repo")
            >>> safe = Path("/home/user/repo/src/file.py")
            >>> unsafe = Path("/home/user/repo/../../../etc/passwd")
            >>> processor.is_safe_path(base, safe)
            True
            >>> processor.is_safe_path(base, unsafe)
            False
        """
        try:
            # Resolve both paths to absolute paths
            base_resolved = base_dir.resolve()
            target_resolved = target_path.resolve()

            # Check if target is relative to base
            return target_resolved.is_relative_to(base_resolved)
        except (ValueError, OSError) as e:
            logger.warning(f"Path validation failed for {target_path}: {e}")
            return False

    def read_file_safe(
        self, file_path: Path, encoding: str = "utf-8", max_size: Optional[int] = None
    ) -> str:
        """
        Safely read file with size limits and error handling.

        For large files, uses streaming to avoid memory issues.

        Args:
            file_path: Path to file
            encoding: File encoding (default: utf-8)
            max_size: Maximum file size in bytes (default: from config)

        Returns:
            File content as string

        Raises:
            FileProcessingError: If file cannot be read
            ValidationError: If file is too large

        Example:
            >>> content = processor.read_file_safe(Path("src/main.py"))
        """
        if not file_path.exists():
            raise FileProcessingError(f"File not found: {file_path}")

        if not file_path.is_file():
            raise FileProcessingError(f"Not a file: {file_path}")

        # Get file size
        file_size = file_path.stat().st_size

        # Check size limit
        max_size = max_size or MAX_FILE_SIZE_BYTES
        if file_size > max_size:
            size_mb = file_size / (1024 * 1024)
            max_mb = max_size / (1024 * 1024)
            raise ValidationError(
                f"File too large: {file_path}", f"Size: {size_mb:.2f}MB, limit: {max_mb:.2f}MB"
            )

        try:
            # For large files, use streaming
            if file_size > STREAM_CHUNK_SIZE * 10:  # > 80KB
                return self._read_file_streaming(file_path, encoding)
            else:
                # For small files, read directly
                with open(file_path, "r", encoding=encoding) as f:
                    return f.read()

        except UnicodeDecodeError as e:
            raise FileProcessingError(
                f"Failed to decode file: {file_path}", f"Encoding: {encoding}, Error: {e}"
            )
        except PermissionError as e:
            raise FileProcessingError(f"Permission denied: {file_path}", str(e))
        except Exception as e:
            raise FileProcessingError(f"Failed to read file: {file_path}", str(e))

    def _read_file_streaming(self, file_path: Path, encoding: str = "utf-8") -> str:
        """
        Read file in chunks to avoid memory issues.

        Args:
            file_path: Path to file
            encoding: File encoding

        Returns:
            File content as string
        """
        chunks = []
        try:
            with open(file_path, "r", encoding=encoding) as f:
                while chunk := f.read(STREAM_CHUNK_SIZE):
                    chunks.append(chunk)
            return "".join(chunks)
        except Exception as e:
            raise FileProcessingError(f"Failed to stream file: {file_path}", str(e))

    def read_file_lines(self, file_path: Path, encoding: str = "utf-8") -> Iterator[str]:
        """
        Read file line by line as generator.

        This is memory-efficient for processing large files.

        Args:
            file_path: Path to file
            encoding: File encoding

        Yields:
            Lines from file

        Example:
            >>> for line in processor.read_file_lines(Path("large.txt")):
            ...     process_line(line)
        """
        try:
            with open(file_path, "r", encoding=encoding) as f:
                for line in f:
                    yield line
        except Exception as e:
            raise FileProcessingError(f"Failed to read file lines: {file_path}", str(e))

    def collect_files(
        self,
        repo_path: Path,
        include_hidden: bool = False,
        include_hidden_paths: Optional[List[str]] = None,
    ) -> List[Path]:
        """
        Collect all files in repository that should be processed.

        Args:
            repo_path: Repository root path
            include_hidden: Whether to include hidden files (default: False)
            include_hidden_paths: Repo-relative glob patterns to include files under hidden paths
                even when include_hidden is False (e.g., ['.claude/**']).

        Returns:
            List of file paths to process

        Example:
            >>> files = processor.collect_files(Path("/path/to/repo"))
            >>> print(f"Found {len(files)} files to process")
        """
        collected_files = []
        include_hidden_paths = include_hidden_paths or []

        for file_path in sorted(repo_path.rglob("*")):
            # Skip non-files
            if not file_path.is_file():
                continue

            # Skip hidden files unless explicitly included
            if not include_hidden:
                # Allow specific hidden files like .cursorrules, .gitignore
                allowed_hidden = {".cursorrules", ".gitignore", ".dockerignore", ".env.example"}

                rel_path = file_path.relative_to(repo_path)
                rel_has_hidden_part = any(part.startswith(".") for part in rel_path.parts)
                rel_is_force_included = posix_glob_match_any(rel_path, include_hidden_paths)

                if (
                    rel_has_hidden_part
                    and file_path.name not in allowed_hidden
                    and not rel_is_force_included
                ):
                    continue

            # Check if should be ignored
            if self.should_ignore(file_path):
                logger.debug(f"Ignoring file: {file_path}")
                continue

            # Validate path safety
            if not self.is_safe_path(repo_path, file_path):
                logger.warning(f"Unsafe path detected, skipping: {file_path}")
                continue

            collected_files.append(file_path)

        logger.info(f"Collected {len(collected_files)} files for processing")
        return collected_files

    def is_text_file(self, file_path: Path) -> bool:
        """
        Check if file is a text file (not binary).

        Args:
            file_path: Path to file

        Returns:
            True if file appears to be text, False otherwise

        Example:
            >>> processor.is_text_file(Path("document.pdf"))
            False
            >>> processor.is_text_file(Path("script.py"))
            True
        """
        # Check extension
        if file_path.suffix in BINARY_EXTENSIONS:
            return False

        if file_path.suffix in IMAGE_EXTENSIONS:
            return False

        # Try to read first few bytes
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(512)

            # Check for null bytes (common in binary files)
            if b"\x00" in chunk:
                return False

            # Try to decode as text
            try:
                chunk.decode("utf-8")
                return True
            except UnicodeDecodeError:
                # Try other encodings
                for encoding in ["latin-1", "gbk", "shift-jis"]:
                    try:
                        chunk.decode(encoding)
                        return True
                    except UnicodeDecodeError:
                        continue

            return False

        except Exception as e:
            logger.debug(f"Could not determine file type for {file_path}: {e}")
            return False

    def get_file_info(self, file_path: Path) -> dict:
        """
        Get file metadata.

        Args:
            file_path: Path to file

        Returns:
            Dictionary with file metadata

        Example:
            >>> info = processor.get_file_info(Path("src/main.py"))
            >>> print(info['size_mb'])
            0.05
        """
        try:
            stats = file_path.stat()
            return {
                "path": file_path,
                "name": file_path.name,
                "extension": file_path.suffix,
                "size_bytes": stats.st_size,
                "size_mb": stats.st_size / (1024 * 1024),
                "modified": stats.st_mtime,
                "is_text": self.is_text_file(file_path),
            }
        except Exception as e:
            logger.warning(f"Could not get file info for {file_path}: {e}")
            return {
                "path": file_path,
                "name": file_path.name,
                "extension": file_path.suffix,
                "error": str(e),
            }
