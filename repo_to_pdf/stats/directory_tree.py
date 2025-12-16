"""Directory tree generation for repository visualization."""

import logging
from pathlib import Path
from typing import Callable, List

logger = logging.getLogger(__name__)


class DirectoryTreeGenerator:
    """Generates visual directory tree structure for repositories."""

    def __init__(self, ignore_patterns: List[str], max_depth: int = 3):
        """
        Initialize the directory tree generator.

        Args:
            ignore_patterns: List of patterns to ignore (e.g., ['node_modules', '*.pyc'])
            max_depth: Maximum depth to traverse (default: 3)
        """
        self.ignore_patterns = ignore_patterns
        self.max_depth = max_depth

    def generate_tree(self, repo_path: Path) -> str:
        """
        Generate directory tree structure as markdown.

        Args:
            repo_path: Root path of the repository

        Returns:
            Markdown formatted directory tree
        """
        tree_lines = ["# 项目结构\n\n```"]
        tree_lines.append(f"{repo_path.name}/")
        tree_lines.extend(self._build_tree(repo_path, depth=0))
        tree_lines.append("```\n")

        return "\n".join(tree_lines)

    def _build_tree(self, current_path: Path, prefix: str = "", depth: int = 0) -> List[str]:
        """
        Recursively build directory tree.

        Args:
            current_path: Current directory path
            prefix: Prefix for tree structure characters
            depth: Current depth level

        Returns:
            List of tree structure lines
        """
        if depth > self.max_depth:
            return []

        items = []

        try:
            # Get all entries and sort (directories first, then files)
            entries = sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))

            for i, entry in enumerate(entries):
                is_last = i == len(entries) - 1

                # Skip hidden files/directories (except special ones)
                if entry.name.startswith(".") and entry.name not in [
                    ".cursorrules",
                    ".gitignore",
                    ".env.example",
                ]:
                    continue

                # Build tree symbols
                if is_last:
                    current_prefix = "└── "
                    extension = "    "
                else:
                    current_prefix = "├── "
                    extension = "│   "

                if entry.is_dir():
                    if not self._should_ignore_dir(entry):
                        items.append(f"{prefix}{current_prefix}{entry.name}/")
                        # Recursively process subdirectories
                        sub_items = self._build_tree(entry, prefix + extension, depth + 1)
                        items.extend(sub_items)
                else:
                    # Check if file should be ignored
                    if not self._should_ignore_file(entry):
                        # Get file size
                        size_str = self._format_file_size(entry)
                        items.append(f"{prefix}{current_prefix}{entry.name} ({size_str})")

        except PermissionError:
            items.append(f"{prefix}[Permission Denied]")

        return items

    def _should_ignore_dir(self, dir_path: Path) -> bool:
        """
        Check if directory should be ignored.

        Args:
            dir_path: Directory path to check

        Returns:
            True if directory should be ignored
        """
        dir_name = dir_path.name

        # Ignore hidden directories
        if dir_name.startswith(".") and dir_name not in [".github"]:
            return True

        # Check against ignore patterns
        for pattern in self.ignore_patterns:
            pattern = pattern.rstrip("/")
            if pattern == dir_name or pattern in str(dir_path):
                return True

        return False

    def _should_ignore_file(self, file_path: Path) -> bool:
        """
        Check if file should be ignored.

        Args:
            file_path: File path to check

        Returns:
            True if file should be ignored
        """
        import fnmatch

        for pattern in self.ignore_patterns:
            # Direct match
            if pattern in str(file_path) or file_path.name == pattern:
                return True

            # Wildcard pattern match
            if "*" in pattern:
                if fnmatch.fnmatch(file_path.name, pattern):
                    return True

        return False

    def _format_file_size(self, file_path: Path) -> str:
        """
        Format file size in human-readable format.

        Args:
            file_path: File path

        Returns:
            Formatted size string (e.g., "1.5KB", "2.3MB")
        """
        try:
            size = file_path.stat().st_size

            if size < 1024:
                return f"{size}B"
            elif size < 1024 * 1024:
                return f"{size / 1024:.1f}KB"
            else:
                return f"{size / (1024 * 1024):.1f}MB"

        except Exception as e:
            logger.debug(f"Failed to get size for {file_path}: {e}")
            return "??"

    def generate_tree_with_filter(
        self, repo_path: Path, filter_func: Callable[[Path], bool]
    ) -> str:
        """
        Generate directory tree with custom filter function.

        Args:
            repo_path: Root path of the repository
            filter_func: Custom filter function (returns True to include)

        Returns:
            Markdown formatted directory tree
        """
        # Temporarily store original ignore check
        original_ignore_file = self._should_ignore_file

        # Override with custom filter
        def custom_filter(file_path: Path) -> bool:
            return not filter_func(file_path) or original_ignore_file(file_path)

        self._should_ignore_file = custom_filter

        try:
            result = self.generate_tree(repo_path)
        finally:
            # Restore original
            self._should_ignore_file = original_ignore_file

        return result
