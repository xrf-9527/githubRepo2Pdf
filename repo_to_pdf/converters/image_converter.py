"""Image conversion utilities for SVG to PNG and remote image handling."""

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

from repo_to_pdf.core.constants import (
    CAIROSVG_HEIGHT,
    CAIROSVG_SCALE,
    CAIROSVG_WIDTH,
    DEFAULT_IMAGE_HEIGHT,
    DEFAULT_IMAGE_WIDTH,
    IMAGE_DOWNLOAD_TIMEOUT,
)
from repo_to_pdf.core.exceptions import ImageProcessingError

logger = logging.getLogger(__name__)


class ImageConverter:
    """Handles image format conversion and remote image downloading."""

    def __init__(self, cache_dir: Path):
        """
        Initialize the image converter.

        Args:
            cache_dir: Directory to store converted and downloaded images
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._conversion_cache: dict[str, str] = {}

    def convert_svg_to_png(
        self, svg_content: str, output_path: Path, use_inkscape_fallback: bool = True
    ) -> bool:
        """
        Convert SVG content to PNG file.

        Args:
            svg_content: Raw SVG content as string
            output_path: Path where PNG should be saved
            use_inkscape_fallback: Whether to try Inkscape if cairosvg fails

        Returns:
            True if conversion succeeded, False otherwise

        Raises:
            ImageProcessingError: If conversion fails critically
        """
        try:
            import cairosvg

            # Remove XML declaration
            svg_content = self._clean_svg_content(svg_content)

            # Check if this is an icon definition file (should be skipped)
            if self._is_icon_definition(svg_content):
                logger.debug("Skipping icon definition SVG file")
                return False

            # Parse and fix SVG dimensions
            svg_content = self._fix_svg_dimensions(svg_content)

            # Convert to PNG with cairosvg
            cairosvg.svg2png(
                bytestring=svg_content.encode("utf-8"),
                write_to=str(output_path),
                parent_width=CAIROSVG_WIDTH,
                parent_height=CAIROSVG_HEIGHT,
                scale=CAIROSVG_SCALE,
            )

            logger.debug(f"Successfully converted SVG to PNG: {output_path}")
            return True

        except Exception as e:
            logger.warning(f"Failed to convert SVG using cairosvg: {e}")

            if use_inkscape_fallback:
                return self._convert_with_inkscape(svg_content, output_path)

            return False

    def _clean_svg_content(self, svg_content: str) -> str:
        """Remove XML declarations and clean SVG content."""
        svg_content = svg_content.replace('<?xml version="1.0" encoding="UTF-8"?>', "")
        svg_content = svg_content.replace('<?xml version="1.0"?>', "")
        return svg_content.strip()

    def _is_icon_definition(self, svg_content: str) -> bool:
        """Check if SVG is an icon definition file (contains <symbol> or only <defs>)."""
        return "<symbol" in svg_content or ("<defs>" in svg_content and "<use" not in svg_content)

    def _fix_svg_dimensions(self, svg_content: str) -> str:
        """
        Parse SVG and ensure it has proper dimensions.

        Args:
            svg_content: Raw SVG content

        Returns:
            SVG content with fixed dimensions

        Raises:
            ImageProcessingError: If SVG parsing fails
        """
        try:
            tree = ET.fromstring(svg_content)
        except ET.ParseError as e:
            raise ImageProcessingError("Failed to parse SVG content", details=str(e))

        # Get current dimensions
        width = tree.get("width", "").strip()
        height = tree.get("height", "").strip()
        viewbox = tree.get("viewBox", "").strip()

        logger.debug(f"Original dimensions - width: {width}, height: {height}, viewBox: {viewbox}")

        # Check if dimensions are zero (invalid)
        if self._is_zero_dimension(width) or self._is_zero_dimension(height):
            logger.debug("Skipping SVG with zero dimensions")
            raise ImageProcessingError("SVG has zero dimensions")

        # Extract dimensions from viewBox if needed
        if viewbox and not (width and height):
            width, height = self._extract_from_viewbox(viewbox, tree)

        # Apply default dimensions if still missing
        if not (tree.get("width") and tree.get("height")):
            tree.set("width", f"{DEFAULT_IMAGE_WIDTH}px")
            tree.set("height", f"{DEFAULT_IMAGE_HEIGHT}px")
            logger.debug(f"Using default dimensions {DEFAULT_IMAGE_WIDTH}x{DEFAULT_IMAGE_HEIGHT}px")

        # Ensure units are present
        self._ensure_units(tree)

        # Convert back to string
        return ET.tostring(tree, encoding="unicode")

    def _is_zero_dimension(self, dimension: str) -> bool:
        """Check if a dimension string represents zero."""
        if not dimension:
            return False
        try:
            value = float(dimension.replace("px", "").strip())
            return value == 0
        except ValueError:
            return False

    def _extract_from_viewbox(self, viewbox: str, tree: ET.Element) -> Tuple[str, str]:
        """Extract width and height from viewBox attribute."""
        try:
            vb_parts = viewbox.split()
            if len(vb_parts) == 4:
                _, _, vb_width, vb_height = vb_parts

                # Check viewBox dimensions aren't zero
                if float(vb_width) == 0 or float(vb_height) == 0:
                    raise ImageProcessingError("ViewBox has zero dimensions")

                tree.set("width", f"{vb_width}px")
                tree.set("height", f"{vb_height}px")
                logger.debug(f"Extracted from viewBox - width: {vb_width}px, height: {vb_height}px")
                return f"{vb_width}px", f"{vb_height}px"
        except (ValueError, ImageProcessingError) as e:
            logger.debug(f"Failed to extract from viewBox: {e}")

        return "", ""

    def _ensure_units(self, tree: ET.Element) -> None:
        """Ensure width and height have units (px)."""
        for dim in ["width", "height"]:
            value = tree.get(dim, "")
            if value and not any(unit in value.lower() for unit in ["px", "pt", "cm", "mm", "in"]):
                tree.set(dim, f"{value}px")
                logger.debug(f"Added px unit to {dim}: {value}px")

    def _convert_with_inkscape(self, svg_content: str, output_path: Path) -> bool:
        """
        Fallback conversion using Inkscape CLI.

        Args:
            svg_content: SVG content to convert
            output_path: Where to save the PNG

        Returns:
            True if successful, False otherwise
        """
        try:
            # Write SVG to temporary file
            temp_svg = output_path.parent / f"temp_{output_path.stem}.svg"
            temp_svg.write_text(svg_content, encoding="utf-8")

            # Run Inkscape command
            inkscape_cmd = [
                "inkscape",
                "--export-type=png",
                f"--export-filename={output_path}",
                "--export-width=1600",
                str(temp_svg),
            ]

            result = subprocess.run(inkscape_cmd, capture_output=True, text=True, timeout=30)

            # Clean up temporary file
            temp_svg.unlink(missing_ok=True)

            if result.returncode == 0 and output_path.exists():
                logger.debug(f"Successfully converted SVG with Inkscape: {output_path}")
                return True

            logger.warning(f"Inkscape conversion failed: {result.stderr}")
            return False

        except Exception as e:
            logger.warning(f"Inkscape fallback conversion failed: {e}")
            return False

    def is_valid_svg(self, content: str) -> bool:
        """
        Check if content is valid SVG.

        Args:
            content: Content to check

        Returns:
            True if valid SVG, False otherwise
        """
        try:
            soup = BeautifulSoup(content, "html.parser")
            svg = soup.find("svg")
            return svg is not None and (svg.get("width") or svg.get("height") or svg.get("viewBox"))
        except Exception:
            return False

    def convert_image_to_png(self, image_path: Path, project_root: Path) -> str:
        """
        Convert image file to PNG if needed.

        Args:
            image_path: Path to image file (can be relative)
            project_root: Root directory of the project

        Returns:
            Relative path to converted PNG, or original path if conversion fails
        """
        try:
            # Resolve path
            if not image_path.is_absolute():
                image_path = project_root / image_path

            if not image_path.exists():
                logger.warning(f"Image file not found: {image_path}")
                return str(image_path)

            # Only convert SVG files
            if not image_path.suffix.lower() == ".svg":
                return str(image_path)

            # Check cache first
            cache_key = str(image_path)
            if cache_key in self._conversion_cache:
                return self._conversion_cache[cache_key]

            # Read SVG content
            svg_content = image_path.read_text(encoding="utf-8")

            # Generate output path
            hash_name = hashlib.md5(svg_content.encode()).hexdigest()
            png_path = self.cache_dir / f"{hash_name}.png"

            # Check if already converted
            if png_path.exists():
                relative_path = f"images/{png_path.name}"
                self._conversion_cache[cache_key] = relative_path
                return relative_path

            # Convert SVG to PNG
            if self.convert_svg_to_png(svg_content, png_path):
                relative_path = f"images/{png_path.name}"
                self._conversion_cache[cache_key] = relative_path
                return relative_path

            return str(image_path)

        except Exception as e:
            logger.warning(f"Failed to convert image {image_path}: {e}")
            return str(image_path)

    def convert_svg_content_to_png(self, svg_content: str) -> Optional[str]:
        """
        Convert SVG content to PNG and return filename.

        Args:
            svg_content: Raw SVG content

        Returns:
            PNG filename if successful, None otherwise
        """
        try:
            # Generate hash-based filename
            hash_name = hashlib.md5(svg_content.encode()).hexdigest()
            png_path = self.cache_dir / f"{hash_name}.png"

            # Check cache
            if png_path.exists():
                return png_path.name

            # Convert
            if self.convert_svg_to_png(svg_content, png_path):
                return png_path.name

            return None

        except Exception as e:
            logger.warning(f"Failed to convert SVG content: {e}")
            return None

    def download_remote_image(self, url: str) -> Optional[str]:
        """
        Download remote image and convert if needed.

        Args:
            url: URL of the remote image

        Returns:
            Relative path to downloaded/converted image, None if failed
        """
        try:
            # Check cache first
            if url in self._conversion_cache:
                return self._conversion_cache[url]

            # Generate hash-based filename
            hash_name = hashlib.md5(url.encode()).hexdigest()

            # Download image
            logger.debug(f"Downloading image: {url}")
            response = requests.get(url, timeout=IMAGE_DOWNLOAD_TIMEOUT)
            response.raise_for_status()

            # Determine content type
            content_type = response.headers.get("Content-Type", "").lower()

            if "svg" in content_type or url.lower().endswith(".svg"):
                # Convert SVG to PNG
                png_path = self.cache_dir / f"{hash_name}.png"

                if png_path.exists():
                    relative_path = f"images/{png_path.name}"
                    self._conversion_cache[url] = relative_path
                    return relative_path

                if self.convert_svg_to_png(response.text, png_path):
                    relative_path = f"images/{png_path.name}"
                    self._conversion_cache[url] = relative_path
                    return relative_path

            else:
                # Save other image formats directly
                ext = self._get_extension_from_content_type(content_type, url)
                local_path = self.cache_dir / f"{hash_name}{ext}"

                if local_path.exists():
                    relative_path = f"images/{local_path.name}"
                    self._conversion_cache[url] = relative_path
                    return relative_path

                local_path.write_bytes(response.content)
                relative_path = f"images/{local_path.name}"
                self._conversion_cache[url] = relative_path
                return relative_path

            return None

        except requests.RequestException as e:
            logger.warning(f"Failed to download remote image {url}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error downloading {url}: {e}")
            return None

    def _get_extension_from_content_type(self, content_type: str, url: str) -> str:
        """Determine file extension from content type or URL."""
        if "image/png" in content_type:
            return ".png"
        elif "image/jpeg" in content_type or "image/jpg" in content_type:
            return ".jpg"
        elif "image/gif" in content_type:
            return ".gif"
        elif "image/webp" in content_type:
            return ".webp"
        else:
            # Try to get extension from URL
            from urllib.parse import urlparse

            path = urlparse(url).path
            ext = Path(path).suffix
            return ext if ext else ".png"

    def clear_cache(self) -> None:
        """Clear the conversion cache."""
        self._conversion_cache.clear()

    def get_cache_stats(self) -> dict[str, int]:
        """Get statistics about the conversion cache."""
        return {
            "cached_conversions": len(self._conversion_cache),
            "files_on_disk": len(list(self.cache_dir.glob("*"))),
        }
