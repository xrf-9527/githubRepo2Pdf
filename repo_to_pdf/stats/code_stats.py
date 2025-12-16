"""Code statistics generation for repository analysis."""

import logging
from pathlib import Path
from typing import Dict, List

from repo_to_pdf.core.constants import CODE_EXTENSIONS

logger = logging.getLogger(__name__)


class CodeStatsGenerator:
    """Generates code statistics for repositories."""

    def __init__(self, ignore_patterns: List[str]):
        """
        Initialize the code stats generator.

        Args:
            ignore_patterns: List of patterns to ignore
        """
        self.ignore_patterns = ignore_patterns

    def generate_stats(self, repo_path: Path) -> str:
        """
        Generate code statistics report as markdown.

        Args:
            repo_path: Root path of the repository

        Returns:
            Markdown formatted statistics report
        """
        stats = self._collect_stats(repo_path)
        return self._format_stats_report(stats)

    def _collect_stats(self, repo_path: Path) -> Dict:
        """
        Collect statistics from repository.

        Args:
            repo_path: Root path of the repository

        Returns:
            Dictionary with statistics data
        """
        stats = {
            "total_files": 0,
            "total_lines": 0,
            "total_size": 0,
            "by_language": {},
            "by_extension": {},
        }

        # Collect statistics
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and not self._should_ignore(file_path):
                stats["total_files"] += 1

                # File size
                try:
                    size = file_path.stat().st_size
                    stats["total_size"] += size
                except Exception as e:
                    logger.debug(f"Failed to get size for {file_path}: {e}")
                    continue

                # Extension statistics
                ext = file_path.suffix.lower()
                if ext:
                    stats["by_extension"][ext] = stats["by_extension"].get(ext, 0) + 1

                    # Language statistics
                    if ext in CODE_EXTENSIONS:
                        lang = CODE_EXTENSIONS[ext]

                        if lang not in stats["by_language"]:
                            stats["by_language"][lang] = {"files": 0, "lines": 0}

                        stats["by_language"][lang]["files"] += 1

                        # Count lines (code files only)
                        lines = self._count_lines(file_path)
                        if lines > 0:
                            stats["total_lines"] += lines
                            stats["by_language"][lang]["lines"] += lines

        return stats

    def _count_lines(self, file_path: Path) -> int:
        """
        Count lines in a file.

        Args:
            file_path: File path

        Returns:
            Number of lines, or 0 if file cannot be read
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return len(f.readlines())
        except UnicodeDecodeError:
            # Binary file, skip
            return 0
        except Exception as e:
            logger.debug(f"Failed to count lines in {file_path}: {e}")
            return 0

    def _should_ignore(self, file_path: Path) -> bool:
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

    def _format_stats_report(self, stats: Dict) -> str:
        """
        Format statistics as markdown report.

        Args:
            stats: Statistics dictionary

        Returns:
            Markdown formatted report
        """
        report = ["# 代码统计\n"]
        report.append(f"- 总文件数：{stats['total_files']:,}")
        report.append(f"- 总代码行数：{stats['total_lines']:,}")
        report.append(f"- 总大小：{stats['total_size'] / (1024 * 1024):.2f} MB\n")

        # Language statistics
        if stats["by_language"]:
            report.append("## 按语言统计\n")
            report.append("| 语言 | 文件数 | 代码行数 |")
            report.append("|------|--------|----------|")

            for lang, data in sorted(
                stats["by_language"].items(), key=lambda x: x[1]["lines"], reverse=True
            ):
                report.append(f"| {lang} | {data['files']} | {data['lines']:,} |")

            report.append("")

        # Extension statistics
        if stats["by_extension"]:
            report.append("## 按文件类型统计\n")
            report.append("| 扩展名 | 文件数 |")
            report.append("|--------|--------|")

            # Show top 20 extensions
            for ext, count in sorted(
                stats["by_extension"].items(), key=lambda x: x[1], reverse=True
            )[:20]:
                report.append(f"| {ext} | {count} |")

            report.append("")

        return "\n".join(report)

    def get_language_breakdown(self, repo_path: Path) -> Dict[str, Dict[str, int]]:
        """
        Get detailed language breakdown.

        Args:
            repo_path: Root path of the repository

        Returns:
            Dictionary mapping language to {files, lines}
        """
        stats = self._collect_stats(repo_path)
        return stats.get("by_language", {})

    def get_total_lines(self, repo_path: Path) -> int:
        """
        Get total lines of code.

        Args:
            repo_path: Root path of the repository

        Returns:
            Total number of lines
        """
        stats = self._collect_stats(repo_path)
        return stats.get("total_lines", 0)

    def get_file_count(self, repo_path: Path) -> int:
        """
        Get total file count.

        Args:
            repo_path: Root path of the repository

        Returns:
            Total number of files
        """
        stats = self._collect_stats(repo_path)
        return stats.get("total_files", 0)
