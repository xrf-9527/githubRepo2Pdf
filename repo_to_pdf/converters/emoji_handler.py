"""Emoji processing and image generation for PDF conversion."""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import requests

from repo_to_pdf.core.constants import EMOJI_DOWNLOAD_TIMEOUT

logger = logging.getLogger(__name__)


class EmojiHandler:
    """Handles emoji detection, downloading, and replacement in text."""

    # Twemoji repository versions to try (in order of preference)
    TWEMOJI_VERSIONS: List[str] = ["v14.0.2", "v14.0.0", "master"]

    # Twemoji CDN URL template
    TWEMOJI_URL_TEMPLATE: str = (
        "https://raw.githubusercontent.com/twitter/twemoji/{version}/assets/svg/{name}.svg"
    )

    def __init__(self, cache_dir: Path, enable_download: bool = True):
        """
        Initialize the emoji handler.

        Args:
            cache_dir: Directory to store emoji PNG files
            enable_download: Whether to download missing emojis from Twemoji
        """
        self.cache_dir = cache_dir / "emoji"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.enable_download = enable_download
        self._emoji_cache: Dict[str, str] = {}
        self._emoji_pattern = self._compile_emoji_regex()

    def _compile_emoji_regex(self) -> re.Pattern:
        """
        Compile emoji detection regex pattern.

        Matches:
        - Basic emoji range (U+1F300-U+1FAFF, U+2600-U+27BF)
        - Optional Variation Selector-16 (U+FE0F)
        - Zero-Width Joiner sequences
        """
        return re.compile(
            r"([\U0001F300-\U0001FAFF\u2600-\u27BF])"  # Basic emoji range
            r"(\uFE0F)?"  # Optional VS16
            r"(?:\u200D[\U0001F300-\U0001FAFF\u2600-\u27BF](\uFE0F)?)*"  # Optional ZWJ sequences
        )

    def _codepoints_to_sequence(self, emoji: str) -> str:
        """
        Convert emoji string to codepoint sequence.

        Args:
            emoji: Emoji character(s)

        Returns:
            Hyphen-separated hex codepoints (e.g., "1f44d" for 👍)

        Example:
            >>> handler._codepoints_to_sequence("👍")
            '1f44d'
            >>> handler._codepoints_to_sequence("👨‍👩‍👧‍👦")
            '1f468-200d-1f469-200d-1f467-200d-1f466'
        """
        return "-".join(f"{ord(ch):x}" for ch in emoji)

    def _generate_fallback_sequences(self, sequence: str) -> List[str]:
        """
        Generate fallback emoji sequences for multi-version support.

        Try these variations in order:
        1. Full sequence with all variation selectors
        2. Sequence without FE0F variation selectors
        3. First codepoint only (base emoji)

        Args:
            sequence: Original codepoint sequence

        Returns:
            List of sequence variants to try
        """
        sequences = [sequence]

        # Remove FE0F variation selectors
        no_fe0f = "-".join(part for part in sequence.split("-") if part != "fe0f")
        if no_fe0f not in sequences:
            sequences.append(no_fe0f)

        # First codepoint only
        first = sequence.split("-")[0]
        if first not in sequences:
            sequences.append(first)

        return sequences

    def ensure_emoji_png(self, emoji_sequence: str) -> Optional[str]:
        """
        Ensure emoji PNG exists, downloading if needed.

        Args:
            emoji_sequence: Emoji codepoint sequence (e.g., "1f44d")

        Returns:
            PNG filename if available, None otherwise
        """
        # Check memory cache
        if emoji_sequence in self._emoji_cache:
            return self._emoji_cache[emoji_sequence]

        # Generate fallback sequences
        sequences = self._generate_fallback_sequences(emoji_sequence)

        # Check if any variant already exists on disk
        for seq in sequences:
            png_path = self.cache_dir / f"{seq}.png"
            if png_path.exists():
                self._emoji_cache[emoji_sequence] = png_path.name
                logger.debug(f"Found cached emoji: {png_path.name}")
                return png_path.name

        # If download disabled, return None
        if not self.enable_download:
            logger.debug(f"Emoji download disabled, skipping: {emoji_sequence}")
            self._emoji_cache[emoji_sequence] = ""
            return None

        # Try downloading from Twemoji
        png_filename = self._download_emoji_svg(sequences)

        # Update cache
        self._emoji_cache[emoji_sequence] = png_filename or ""
        return png_filename

    def _download_emoji_svg(self, sequences: List[str]) -> Optional[str]:
        """
        Download emoji SVG from Twemoji and convert to PNG.

        Args:
            sequences: List of emoji sequence variants to try

        Returns:
            PNG filename if successful, None otherwise
        """
        svg_bytes = None
        chosen_name = None

        # Try each Twemoji version
        for version in self.TWEMOJI_VERSIONS:
            # Try each sequence variant
            for seq in sequences:
                url = self.TWEMOJI_URL_TEMPLATE.format(version=version, name=seq)

                try:
                    logger.debug(f"Trying emoji download: {url}")
                    response = requests.get(url, timeout=EMOJI_DOWNLOAD_TIMEOUT)

                    if response.status_code == 200 and response.content:
                        svg_bytes = response.content
                        chosen_name = seq
                        logger.debug(f"Successfully downloaded emoji: {seq} from {version}")
                        break

                except requests.RequestException as e:
                    logger.debug(f"Failed to download {url}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Unexpected error downloading {url}: {e}")
                    continue

            # Break outer loop if found
            if svg_bytes:
                break

        # No SVG found
        if not svg_bytes or not chosen_name:
            logger.debug(f"Could not download emoji for sequences: {sequences}")
            return None

        # Convert SVG to PNG
        return self._convert_emoji_svg_to_png(svg_bytes, chosen_name)

    def _convert_emoji_svg_to_png(self, svg_bytes: bytes, name: str) -> Optional[str]:
        """
        Convert emoji SVG bytes to PNG file.

        Args:
            svg_bytes: SVG content as bytes
            name: Emoji sequence name (for filename)

        Returns:
            PNG filename if successful, None otherwise
        """
        try:
            import cairosvg

            png_filename = f"{name}.png"
            png_path = self.cache_dir / png_filename

            cairosvg.svg2png(bytestring=svg_bytes, write_to=str(png_path))

            logger.debug(f"Converted emoji to PNG: {png_filename}")
            return png_filename

        except ImportError:
            logger.error("cairosvg not installed, cannot convert emoji SVG to PNG")
            return None
        except Exception as e:
            logger.warning(f"Failed to convert emoji SVG to PNG: {e}")
            return None

    def replace_emoji_in_text(self, text: str, in_code: bool = False) -> str:
        """
        Replace emoji characters in text with LaTeX image commands.

        Args:
            text: Text containing emoji
            in_code: If True, use code-safe syntax (§emojiimg«...»)
                    If False, use normal LaTeX syntax (\\emojiimg{...})

        Returns:
            Text with emoji replaced by image references
        """
        try:

            def replace_match(match: re.Match) -> str:
                emoji = match.group(0)
                sequence = self._codepoints_to_sequence(emoji)

                # Ensure PNG exists
                png_filename = self.ensure_emoji_png(sequence)

                if png_filename:
                    # Use standard LaTeX command form in both code and text.
                    # In code blocks, our Verbatim environment allows commands
                    # (commandchars=\\{\\}) so this will render inline images.
                    return f"\\emojiimg{{{png_filename}}}"

                # Return original emoji if PNG not available
                return emoji

            return self._emoji_pattern.sub(replace_match, text)

        except Exception as e:
            logger.warning(f"Failed to replace emoji in text: {e}")
            return text

    def replace_emoji_in_code(self, text: str) -> str:
        """
        Replace emoji in code blocks. Uses standard LaTeX form too so that
        Highlighting/Verbatim can render images inline.

        Args:
            text: Code text containing emoji

        Returns:
            Text with emoji replaced using code-safe syntax
        """
        return self.replace_emoji_in_text(text, in_code=True)

    def clear_cache(self) -> None:
        """Clear the emoji memory cache."""
        self._emoji_cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get emoji cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "cached_sequences": len(self._emoji_cache),
            "files_on_disk": len(list(self.cache_dir.glob("*.png"))),
            "cache_size_bytes": sum(f.stat().st_size for f in self.cache_dir.glob("*.png")),
        }

    def preload_common_emojis(self) -> int:
        """
        Preload commonly used emojis to speed up processing.

        Returns:
            Number of emojis successfully preloaded
        """
        # Common emojis by codepoint
        common_emojis = [
            "2705",  # ✅ white heavy check mark
            "274c",  # ❌ cross mark
            "26a0",  # ⚠️ warning
            "2139",  # ℹ️ information
            "1f4dd",  # 📝 memo
            "1f4c4",  # 📄 page facing up
            "1f4ca",  # 📊 bar chart
            "1f527",  # 🔧 wrench
            "1f4e6",  # 📦 package
            "1f680",  # 🚀 rocket
            "1f389",  # 🎉 party popper
            "1f44d",  # 👍 thumbs up
            "1f44e",  # 👎 thumbs down
        ]

        loaded = 0
        for emoji_seq in common_emojis:
            if self.ensure_emoji_png(emoji_seq):
                loaded += 1

        logger.info(f"Preloaded {loaded}/{len(common_emojis)} common emojis")
        return loaded

    def is_emoji(self, text: str) -> bool:
        """
        Check if text contains emoji.

        Args:
            text: Text to check

        Returns:
            True if text contains emoji, False otherwise
        """
        return bool(self._emoji_pattern.search(text))

    def extract_emojis(self, text: str) -> List[str]:
        """
        Extract all emoji from text.

        Args:
            text: Text to extract emoji from

        Returns:
            List of emoji characters found
        """
        return self._emoji_pattern.findall(text)
