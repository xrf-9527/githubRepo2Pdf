"""Markdown processing utilities for PDF conversion."""

import logging
import re
from pathlib import Path
from typing import Dict, Optional

from bs4 import BeautifulSoup

from repo_to_pdf.converters.image_converter import ImageConverter
from repo_to_pdf.core.config import AppConfig

logger = logging.getLogger(__name__)


class MarkdownProcessor:
    """Processes Markdown content for PDF conversion."""

    def __init__(self, config: AppConfig, image_converter: ImageConverter):
        """
        Initialize the markdown processor.

        Args:
            config: Application configuration
            image_converter: Image converter instance for handling images
        """
        self.config = config
        self.image_converter = image_converter
        self.max_line_length = config.pdf_settings.max_line_length

    def process_markdown_content(
        self, content: str, source_file: Optional[Path] = None, repo_root: Optional[Path] = None
    ) -> str:
        """
        Process Markdown content for PDF generation.

        Steps:
        1. Remove code block title attributes
        2. Process reference-style image links
        3. Process inline images (both remote and local)
        4. Process HTML image tags
        5. Process inline SVG
        6. Escape backslash-u sequences outside code
        7. Hard-wrap long lines in code blocks
        8. Escape YAML delimiters

        Args:
            content: Markdown content to process
            source_file: Path to source markdown file (for relative path resolution)
            repo_root: Repository root path

        Returns:
            Processed markdown content
        """
        # 1. Remove code block title attributes
        content = self._remove_code_block_titles(content)

        # 2. Process reference-style links
        reference_links = self._extract_reference_links(content)
        content = self._process_reference_images(content, reference_links, source_file, repo_root)

        # 3. Process inline images
        content = self._process_inline_images(content, source_file, repo_root)

        # 4. Process HTML image tags
        content = self._process_html_images(content, source_file, repo_root)

        # 5. Process inline SVG
        content = self._process_inline_svg(content)

        # 6. Escape backslash-u sequences outside code blocks
        content = self._escape_backslash_u_sequences(content)

        # 7. Hard-wrap long lines in code blocks
        content = self._hard_wrap_code_blocks(content)

        # 8. Escape YAML delimiters
        content = self._escape_yaml_delimiters(content)

        # 9. Final scrub of any remaining remote images to avoid Pandoc fetching
        content = self._remove_residual_remote_images(content)

        return content

    def _remove_code_block_titles(self, content: str) -> str:
        """Remove title attributes from code blocks."""
        return re.sub(r'```(\w+)\s+title="([^"]+)"', r"```\1", content)

    def _extract_reference_links(self, content: str) -> Dict[str, Dict[str, Optional[str]]]:
        """
        Extract reference-style link definitions.

        Args:
            content: Markdown content

        Returns:
            Dictionary mapping reference IDs to {url, title}
        """
        reference_links = {}

        for match in re.finditer(r'^\[(.*?)\]:\s*(\S+)(?:\s+"(.*?)")?$', content, re.MULTILINE):
            ref_id, url, title = match.groups()
            reference_links[ref_id] = {"url": url, "title": title}

        return reference_links

    def _process_reference_images(
        self,
        content: str,
        reference_links: Dict[str, Dict[str, Optional[str]]],
        source_file: Optional[Path],
        repo_root: Optional[Path],
    ) -> str:
        """Process reference-style image links."""

        def process_ref_image(match: re.Match) -> str:
            alt = match.group(1) or ""
            ref_id = match.group(2)

            if ref_id not in reference_links:
                return match.group(0)

            ref = reference_links[ref_id]
            url = ref["url"]
            title = ref["title"]

            # Process remote images
            if url.startswith(("http://", "https://")):
                new_path = self.image_converter.download_remote_image(url)
                if new_path:
                    if title:
                        return f'![{alt}]({new_path} "{title}")'
                    return f"![{alt}]({new_path})"
                return ""

            # Process local SVG
            if url.lower().endswith(".svg"):
                new_path = self.image_converter.convert_image_to_png(
                    Path(url), self.config.project_root
                )
                if title:
                    return f'![{alt}]({new_path} "{title}")'
                return f"![{alt}]({new_path})"

            # Normalize other local images to temp images directory (flattened)
            img_path = self._resolve_image_path(url, source_file, repo_root)
            if img_path and img_path.exists():
                normalized = f"images/{img_path.name}"
                if title:
                    return f'![{alt}]({normalized} "{title}")'
                return f"![{alt}]({normalized})"

            # Fallback: keep as-is
            if title:
                return f'![{alt}]({url} "{title}")'
            return f"![{alt}]({url})"

        return re.sub(r"!\[(.*?)\]\[(.*?)\]", process_ref_image, content)

    def _process_inline_images(
        self, content: str, source_file: Optional[Path], repo_root: Optional[Path]
    ) -> str:
        """Process inline image syntax."""

        def process_md_image(match: re.Match) -> str:
            alt = match.group(1) or ""
            path = match.group(2)
            # title is group 3 if it exists
            title = ""
            if len(match.groups()) > 2 and match.group(3):
                title = match.group(3)

            # Process remote images
            if path.startswith(("http://", "https://")):
                new_path = self.image_converter.download_remote_image(path)
                if new_path:
                    if title:
                        return f'![{alt}]({new_path} "{title}")'
                    return f"![{alt}]({new_path})"
                return ""  # Remove if download fails

            # Process local SVG
            if path.lower().endswith(".svg"):
                img_path = self._resolve_image_path(path, source_file, repo_root)
                if img_path:
                    new_path = self.image_converter.convert_image_to_png(
                        img_path, repo_root or self.config.project_root
                    )
                    if title:
                        return f'![{alt}]({new_path} "{title}")'
                    return f"![{alt}]({new_path})"

            # Process other local images (JPG, PNG, etc.)
            # Try to resolve the path for local images
            if not path.startswith(("http://", "https://")):
                img_path = self._resolve_image_path(path, source_file, repo_root)
                if img_path and img_path.exists():
                    # Normalize to temp images directory (flattened) to align with LaTeX \graphicspath
                    normalized = f"images/{img_path.name}"
                    if title:
                        return f'![{alt}]({normalized} "{title}")'
                    return f"![{alt}]({normalized})"
                else:
                    # Image not found locally, remove the reference to avoid Pandoc error
                    logger.warning(f"Image not found, removing reference: {path}")
                    return ""

            return match.group(0)

        # Process with title
        content = re.sub(r'!\[(.*?)\]\((.*?)\s+"(.*?)"\)', process_md_image, content)
        # Process without title
        content = re.sub(r"!\[(.*?)\]\((.*?)\)", process_md_image, content)

        return content

    def _resolve_image_path(
        self, img_path: str, source_file: Optional[Path], repo_root: Optional[Path]
    ) -> Optional[Path]:
        """
        Resolve relative image path to absolute path.

        Args:
            img_path: Image path from markdown
            source_file: Source markdown file
            repo_root: Repository root

        Returns:
            Resolved absolute path if found, None otherwise
        """
        if not source_file or not repo_root:
            return None

        # Handle absolute paths (starting with /)
        if img_path.startswith("/"):
            img_path = img_path.lstrip("/")

        # Try multiple path resolution strategies
        possible_paths = [
            # 1. Relative to source file directory
            source_file.parent / img_path,
            # 2. Relative to repo root
            repo_root / img_path,
            # 3. Resolved relative paths
            (source_file.parent / img_path).resolve(),
            # 4. Strip ./ prefix
            (source_file.parent / img_path.lstrip("./")).resolve(),
            # 5. From repo root without ./
            repo_root / img_path.lstrip("./"),
        ]

        for path in possible_paths:
            try:
                if path.exists():
                    return path
            except Exception as e:
                logger.debug(f"Failed to check path {path}: {e}")

        logger.warning(f"Could not resolve image path: {img_path}")
        return None

    def _process_html_images(
        self, content: str, source_file: Optional[Path], repo_root: Optional[Path]
    ) -> str:
        """Process HTML <img> tags and convert to Markdown.

        - Resolves local paths (including repo-root absolute like /images/...) against
          the repo so Pandoc can locate them.
        - Downloads remote images when enabled.
        - Converts local SVG images to PNG via the image converter cache.
        """

        def process_html_image(match: re.Match) -> str:
            tag = match.group(0)
            soup = BeautifulSoup(tag, "html.parser")
            img = soup.find("img")

            if not img:
                return tag

            src = img.get("src", "")
            alt = img.get("alt", "")

            if not src:
                return ""

            # Handle remote images (download; if blocked, drop to avoid Pandoc fetching)
            if src.startswith(("http://", "https://")):
                # Download remote image
                new_path = self.image_converter.download_remote_image(src)
                if new_path:
                    return f"![{alt}]({new_path})"
                # If download fails (e.g., no network), drop the image to prevent Pandoc errors
                return ""

            # Resolve local path relative to source file and repo root
            resolved = self._resolve_image_path(src, source_file, repo_root)
            if not resolved:
                logger.warning(f"Could not resolve HTML image path: {src}")
                return ""  # drop unresolved image to avoid Pandoc failure

            # Handle local SVG via converter (returns images/<hash>.png)
            if resolved.suffix.lower() == ".svg":
                new_src = self.image_converter.convert_image_to_png(
                    resolved, repo_root or self.config.project_root
                )
                return f"![{alt}]({new_src})"

            # Normalize other local images to temp images directory (flattened)
            normalized = f"images/{resolved.name}"
            return f"![{alt}]({normalized})"

        return re.sub(r"<img\s+[^>]+>", process_html_image, content, flags=re.IGNORECASE)

    def _remove_residual_remote_images(self, content: str) -> str:
        """
        Remove any leftover remote images that earlier passes didn't catch.

        This prevents Pandoc from trying to fetch URLs during PDF build, which
        can fail in restricted environments and produce broken temp files.
        """
        # Remove Markdown inline remote images: ![alt](http...)
        content = re.sub(r"!\[[^\]]*\]\((https?://[^\s)]+)(\s+\"[^\"]*\")?\)", "", content)
        # Remove HTML remote images: <img src="http...">
        content = re.sub(
            r"<img[^>]+src=\"https?://[^\"]+\"[^>]*>", "", content, flags=re.IGNORECASE
        )
        return content

    def _process_inline_svg(self, content: str) -> str:
        """Process inline <svg> tags."""

        def process_svg(match: re.Match) -> str:
            svg_content = match.group(0)

            if self.image_converter.is_valid_svg(svg_content):
                png_filename = self.image_converter.convert_svg_content_to_png(svg_content)
                if png_filename:
                    # Inline SVGs are converted to the shared images/ cache directory
                    return f"![](images/{png_filename})"

            return match.group(0)

        return re.sub(
            r"<svg\s*.*?>.*?</svg>", process_svg, content, flags=re.DOTALL | re.IGNORECASE
        )

    def _escape_backslash_u_sequences(self, content: str) -> str:
        """
        Escape backslashes in code blocks.
        
        Since we enabled commandchars=\\\\\\{\\} in LaTeX Highlighting environment
        (to support emojis), we must escape literal backslashes in code blocks
        as they would otherwise be interpreted as command starts.
        
        Outside code blocks, we rely on Pandoc (with raw_tex disabled) to 
        correctly escape backslashes in text.
        """
        lines = content.splitlines()
        out = []
        in_code = False
        fence = None

        for ln in lines:
            if not in_code:
                # Check if entering code block
                m = re.match(r"^(?P<fence>```+)(?P<info>.*)$", ln)
                if m:
                    in_code = True
                    fence = m.group("fence")
                    out.append(ln)
                    continue
                
                # Outside code block: Do nothing (Pandoc handles escaping)
                out.append(ln)
            else:
                # In code block
                if ln.startswith(fence):
                    try:
                        # Check if it's really the end fence (length match or longer)
                        # Standard markdown allows end fence to be longer
                        if len(ln.split()[0]) >= len(fence):
                            in_code = False
                            fence = None
                            out.append(ln)
                            continue
                    except IndexError:
                        pass
                
                # Escape backslashes in code content
                # \ -> \\
                out.append(ln.replace("\\", "\\\\"))

        return "\n".join(out)

    def _hard_wrap_code_blocks(self, content: str) -> str:
        """
        Hard-wrap long lines in fenced code blocks.

        This prevents Verbatim overflow in LaTeX.
        """
        lines = content.splitlines()
        out = []
        in_code = False
        fence = None
        skip_block = False

        hard_wrap_threshold = max(40, self.max_line_length)
        wrap_width = max(40, min(160, int(self.max_line_length * 0.75)))

        for ln in lines:
            if not in_code:
                # Check if entering code block
                m = re.match(r"^(?P<fence>```+)(?P<info>.*)$", ln)
                if m:
                    info = (m.group("info") or "").strip().lower()
                    fence = m.group("fence")
                    in_code = True
                    out.append(ln)

                    # Skip raw LaTeX blocks
                    skip_block = "{=latex}" in info or info == "latex"
                    if skip_block:
                        fence = fence + "|SKIP"
                    continue

                out.append(ln)
            else:
                # Check if exiting code block
                fence_check = fence if "SKIP" not in fence else fence.split("|")[0]
                if ln.startswith(fence_check):
                    in_code = False
                    out.append(ln)
                    fence = None
                    skip_block = False
                    continue

                # Process code line
                if skip_block:
                    out.append(ln)
                else:
                    # Hard wrap long lines
                    if len(ln) > hard_wrap_threshold:
                        wrapped = "\n".join(
                            ln[i : i + wrap_width] for i in range(0, len(ln), wrap_width)
                        )
                        out.append(wrapped)
                    else:
                        out.append(ln)

        return "\n".join(out)

    def _escape_yaml_delimiters(self, content: str) -> str:
        """
        Escape standalone --- lines to prevent pandoc from treating them as YAML delimiters.
        """
        return re.sub(r"^---$", r"\\---", content, flags=re.MULTILINE)
