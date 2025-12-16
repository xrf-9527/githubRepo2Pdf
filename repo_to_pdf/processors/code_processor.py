"""Code processing utilities for syntax highlighting and formatting."""

import logging
import re
from typing import List, Tuple

from repo_to_pdf.converters.emoji_handler import EmojiHandler
from repo_to_pdf.core.config import AppConfig
from repo_to_pdf.core.constants import (
    CHUNK_SIZE_LINES,
    MAX_LINE_LENGTH_DEFAULT,
    MAX_LINES_BEFORE_SPLIT,
)

logger = logging.getLogger(__name__)


class CodeProcessor:
    """Processes code files for PDF conversion with syntax highlighting."""

    # File extensions that use C-style comments (// and /* */)
    C_LIKE_EXTENSIONS = {
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".cpp",
        ".c",
        ".go",
        ".cs",
        ".php",
    }

    # File extensions that use # for comments
    SHARP_EXTENSIONS = {
        ".py",
        ".sh",
        ".bash",
        ".zsh",
        ".rb",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
    }

    # File extensions that use -- for comments
    SQL_EXTENSIONS = {".sql"}

    def __init__(self, config: AppConfig, emoji_handler: EmojiHandler):
        """
        Initialize the code processor.

        Args:
            config: Application configuration
            emoji_handler: Emoji handler for replacing emoji in code
        """
        self.config = config
        self.emoji_handler = emoji_handler
        self.max_line_length = config.pdf_settings.max_line_length
        self.split_large_files = config.pdf_settings.split_large_files
        self.render_header_comments_outside = (
            config.pdf_settings.render_header_comments_outside_code
        )
        self.code_block_strategy = config.pdf_settings.code_block_strategy

    def process_code_file(self, content: str, file_extension: str, relative_path: str) -> str:
        """
        Process code file content for PDF conversion.

        Steps:
        1. Extract header comments (if enabled)
        2. Process long lines
        3. Replace emoji with image references
        4. Split large files (if needed)
        5. Format with appropriate code block syntax

        Args:
            content: Code file content
            file_extension: File extension (e.g., '.py')
            relative_path: Relative path from repo root

        Returns:
            Formatted markdown with code blocks
        """
        # 1. Extract header comments
        header_md = ""
        code_body = content

        if self.render_header_comments_outside:
            header_text, code_body = self.extract_header_comment(code_body, file_extension)
            if header_text:
                # Replace emoji in header (use normal LaTeX syntax)
                header_text = self.emoji_handler.replace_emoji_in_text(header_text, in_code=False)
                header_md = header_text.strip() + "\n\n"

        # 2. Process long lines
        code_body = self.process_long_lines(code_body)

        # 3. Hard wrap very long lines
        code_body = self._hard_wrap_lines(code_body)

        # 4. Replace emoji in code (use code-safe syntax)
        code_transformed = self.emoji_handler.replace_emoji_in_code(code_body)
        contains_emoji = "\\emojiimg{" in code_transformed

        # 5. Get language for syntax highlighting
        from repo_to_pdf.core.constants import CODE_EXTENSIONS

        lang = CODE_EXTENSIONS.get(file_extension, "text")

        # 6. Handle large files
        lines = code_transformed.splitlines()

        if len(lines) > MAX_LINES_BEFORE_SPLIT:
            if self.split_large_files:
                # Split into parts
                head = f"\n\n# {relative_path}\n\n" + header_md
                parts = self._split_large_file(relative_path, lines, lang)
                return head + parts
            else:
                # Truncate
                code_transformed = (
                    "\n".join(lines[:MAX_LINES_BEFORE_SPLIT]) + "\n\n... (文件太大，已截断)"
                )

        # 7. Format output
        return self._format_code_output(
            relative_path, header_md, code_transformed, lang, contains_emoji
        )

    def extract_header_comment(self, content: str, file_extension: str) -> Tuple[str, str]:
        """
        Extract header comment block from code file.

        Only processes typical languages with:
        - C-style: // and /* */
        - Script/Config: #
        - SQL: --

        Stops at first blank line or non-comment line.

        Args:
            content: File content
            file_extension: File extension

        Returns:
            Tuple of (header_text, remaining_code)
        """
        lines = content.splitlines()
        if not lines:
            return "", content

        def is_blank(idx: int) -> bool:
            return idx < len(lines) and lines[idx].strip() == ""

        def starts_with(idx: int, prefix: str) -> bool:
            return idx < len(lines) and lines[idx].lstrip().startswith(prefix)

        def strip_line_comment(s: str, marker: str) -> str:
            """Remove comment marker and following space."""
            t = s.lstrip()
            if t.startswith(marker):
                return t[len(marker) :].lstrip()
            return s

        # Don't extract if first line is blank
        if is_blank(0):
            return "", content

        header_chunks: List[str] = []
        i = 0
        n = len(lines)

        if file_extension in self.C_LIKE_EXTENSIONS:
            # Handle block comment /* */
            if starts_with(0, "/*"):
                buf = []
                line = lines[i].lstrip()

                # Remove opening /*
                if line.startswith("/*"):
                    line = line[2:]

                # Read until */
                while i < n:
                    end_pos = line.find("*/")
                    if end_pos != -1:
                        buf.append(line[:end_pos])
                        i += 1
                        break
                    buf.append(line)
                    i += 1
                    if i < n:
                        line = lines[i]

                header_chunks.append("\n".join(buf))

                # Continue with // comments after block comment
                while i < n and lines[i].lstrip().startswith("//"):
                    header_chunks.append(strip_line_comment(lines[i], "//"))
                    i += 1

                # Skip trailing blank line
                if i < n and lines[i].strip() == "":
                    i += 1

            # Handle // comments
            elif starts_with(0, "//"):
                while i < n and lines[i].lstrip().startswith("//"):
                    header_chunks.append(strip_line_comment(lines[i], "//"))
                    i += 1
            else:
                return "", content

        elif file_extension in self.SHARP_EXTENSIONS:
            if lines[0].lstrip().startswith("#"):
                while i < n and lines[i].lstrip().startswith("#"):
                    header_chunks.append(strip_line_comment(lines[i], "#"))
                    i += 1
            else:
                return "", content

        elif file_extension in self.SQL_EXTENSIONS:
            if lines[0].lstrip().startswith("--"):
                while i < n and lines[i].lstrip().startswith("--"):
                    header_chunks.append(strip_line_comment(lines[i], "--"))
                    i += 1
            else:
                return "", content

        else:
            # Unsupported language
            return "", content

        # Skip trailing blank line
        if i < n and lines[i].strip() == "":
            i += 1

        header_text = "\n".join(h.rstrip() for h in header_chunks).strip()
        remaining = "\n".join(lines[i:])

        return header_text, remaining

    def process_long_lines(self, content: str, max_length: int = MAX_LINE_LENGTH_DEFAULT) -> str:
        """
        Process long lines by breaking them intelligently.

        Args:
            content: Code content
            max_length: Maximum line length threshold

        Returns:
            Content with long lines processed
        """
        lines = []

        for line in content.splitlines():
            if len(line) <= max_length:
                lines.append(line)
                continue

            # Check if line contains arrays
            if "[" in line and "]" in line:
                lines.append(self._break_array_line(line, max_length))
            # Check if line contains long strings
            elif '"' in line or "'" in line:
                lines.append(self._break_long_strings(line))
            else:
                lines.append(line)

        return "\n".join(lines)

    def _break_array_line(self, line: str, max_length: int) -> str:
        """Break array line at commas."""
        indent = " " * (len(line) - len(line.lstrip()))
        parts = line.split(",")
        formatted_parts = []
        current_line = parts[0]

        for part in parts[1:]:
            if len(current_line + "," + part) > max_length:
                formatted_parts.append(current_line + ",")
                current_line = indent + part.lstrip()
            else:
                current_line += "," + part

        formatted_parts.append(current_line)
        return "\n".join(formatted_parts)

    def _break_long_strings(self, line: str) -> str:
        """Break lines with long strings."""
        # Find long strings (100+ characters)
        pattern = r'["\']([^"\']{100,})["\']'

        def replacer(match: re.Match) -> str:
            s = match.group(1)
            indent = " " * (len(line) - len(line.lstrip()))
            parts = [s[i : i + 80] for i in range(0, len(s), 80)]

            if len(parts) > 1:
                quote = match.group(0)[0]  # Get original quote
                return f"{quote}\\\n{indent}".join(parts) + quote

            return match.group(0)

        return re.sub(pattern, replacer, line)

    def _hard_wrap_lines(self, content: str) -> str:
        """Hard wrap extremely long lines to prevent overflow."""
        hard_wrap_threshold = max(40, self.max_line_length)
        wrap_width = max(40, min(160, int(self.max_line_length * 0.75)))

        lines = []
        for ln in content.splitlines():
            if len(ln) > hard_wrap_threshold:
                wrapped = "\n".join(ln[i : i + wrap_width] for i in range(0, len(ln), wrap_width))
                lines.append(wrapped)
            else:
                lines.append(ln)

        return "\n".join(lines)

    def _split_large_file(self, relative_path: str, lines: List[str], lang: str) -> str:
        """
        Split large file into multiple parts.

        Args:
            relative_path: Relative file path
            lines: File content lines
            lang: Language for syntax highlighting

        Returns:
            Markdown with split file parts
        """
        result = []
        total_lines = len(lines)
        num_parts = (total_lines + CHUNK_SIZE_LINES - 1) // CHUNK_SIZE_LINES

        # Add file note
        result.append(f"\n> 注意：此文件包含 {total_lines} 行，已分为 {num_parts} 个部分显示\n")

        # Split into parts
        for i in range(num_parts):
            start = i * CHUNK_SIZE_LINES
            end = min((i + 1) * CHUNK_SIZE_LINES, total_lines)
            part_content = "\n".join(lines[start:end])

            # Add part header
            result.append(f"\n## {relative_path} - 第 {i+1}/{num_parts} 部分 (行 {start+1}-{end})")

            # Format part
            if "§emojiimg" in part_content:
                result.append("\n```{=latex}\n")
                result.append("\\begin{CodeBlock}\n")
                result.append(part_content)
                result.append("\n\\end{CodeBlock}\n")
                result.append("```\n")
            else:
                result.append(f"\n`````{lang}\n")
                result.append(part_content)
                result.append("\n`````\n")

        return "".join(result)

    def _format_code_output(
        self,
        relative_path: str,
        header_md: str,
        code_content: str,
        lang: str,
        contains_emoji: bool,
    ) -> str:
        """
        Format code output with appropriate code block syntax.

        Args:
            relative_path: Relative file path
            header_md: Header comment markdown
            code_content: Processed code content
            lang: Language for syntax highlighting
            contains_emoji: Whether code contains emoji

        Returns:
            Formatted markdown
        """
        head = f"\n\n# {relative_path}\n\n" + header_md

        # Render with regular code blocks; inline \emojiimg will be executed
        # by the Verbatim/Highlighting environment (commandchars=\\{\\}).
        return head + f"`````{lang}\n{code_content}\n`````\n\n"

    def should_skip_file(self, content: str) -> bool:
        """
        Check if file should be skipped based on content.

        Args:
            content: File content

        Returns:
            True if file should be skipped
        """
        # Skip files containing SVG (likely icon files)
        return "<svg" in content
