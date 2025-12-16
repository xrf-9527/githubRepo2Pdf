"""Main PDF converter coordinating all components."""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from tqdm import tqdm

from repo_to_pdf.converters import EmojiHandler, ImageConverter, LaTeXGenerator
from repo_to_pdf.core.config import AppConfig
from repo_to_pdf.core.constants import CODE_EXTENSIONS, IMAGE_EXTENSIONS
from repo_to_pdf.core.exceptions import ConversionError, GitOperationError
from repo_to_pdf.git.repo_manager import GitRepoManager
from repo_to_pdf.processors import CodeProcessor, FileProcessor, MarkdownProcessor
from repo_to_pdf.stats import CodeStatsGenerator, DirectoryTreeGenerator

logger = logging.getLogger(__name__)


class RepoPDFConverter:
    """
    Main converter coordinating all components to convert repository to PDF.

    This class orchestrates the entire conversion process:
    1. Clone/update repository
    2. Collect and process files
    3. Generate statistics and directory tree
    4. Convert Markdown to PDF using Pandoc
    """

    def __init__(self, config: AppConfig):
        """
        Initialize the PDF converter.

        Args:
            config: Application configuration
        """
        self.config = config

        # Initialize directories
        self.workspace_dir = config.workspace_path
        self.output_dir = config.output_path
        self.temp_dir = config.project_root / "temp_conversion_files"

        # Create directories
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Initialize image and emoji cache directories
        self.images_dir = self.temp_dir / "images"
        self.images_dir.mkdir(exist_ok=True)

        # Initialize components
        self.file_processor = FileProcessor(config)
        self.image_converter = ImageConverter(self.images_dir)
        self.emoji_handler = EmojiHandler(
            self.images_dir, enable_download=config.pdf_settings.emoji_download
        )
        self.markdown_processor = MarkdownProcessor(config, self.image_converter)
        self.code_processor = CodeProcessor(config, self.emoji_handler)
        self.latex_generator = LaTeXGenerator(config, self.temp_dir)
        self.tree_generator = DirectoryTreeGenerator(
            config.ignores, max_depth=config.pdf_settings.tree_max_depth
        )
        self.stats_generator = CodeStatsGenerator(config.ignores)

        # Repository manager (initialized in convert())
        self.repo_manager: Optional[GitRepoManager] = None
        self.repo_path: Optional[Path] = None

    def convert(self) -> Path:
        """
        Convert repository to PDF.

        Returns:
            Path to generated PDF file

        Raises:
            GitOperationError: If git operations fail
            ConversionError: If PDF conversion fails
        """
        try:
            # Step 1: Clone or update repository
            self.repo_path = self._clone_or_update_repository()
            logger.info(f"Repository ready at: {self.repo_path}")

            # Step 2: Generate intermediate Markdown
            temp_md = self._generate_markdown()
            logger.info(f"Generated Markdown: {temp_md}")

            # Step 3: Generate LaTeX configuration
            pandoc_config = self.latex_generator.generate_pandoc_config(self.repo_path.name)
            logger.info(f"Generated Pandoc config: {pandoc_config}")

            # Step 4: Generate PDF using Pandoc
            output_pdf = self._generate_pdf(temp_md, pandoc_config)
            logger.info(f"✅ PDF generated successfully: {output_pdf}")

            return output_pdf

        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            raise ConversionError("Failed to convert repository to PDF", details=str(e))

    def _clone_or_update_repository(self) -> Path:
        """
        Clone or update the repository.

        Returns:
            Path to cloned repository

        Raises:
            GitOperationError: If git operations fail
        """
        try:
            self.repo_manager = GitRepoManager(
                self.config.repository.url, self.config.repository.branch
            )

            repo_path = self.repo_manager.clone_or_pull(self.workspace_dir)
            return repo_path

        except Exception as e:
            raise GitOperationError(
                f"Failed to clone/update repository: {self.config.repository.url}",
                details=str(e),
            )

    def _generate_markdown(self) -> Path:
        """
        Generate intermediate Markdown file with all content.

        Returns:
            Path to generated Markdown file
        """
        temp_md = self.temp_dir / "temp.md"

        with open(temp_md, "w", encoding="utf-8") as out_file:
            # Write title
            out_file.write(f"# {self.repo_path.name} 代码文档\n\n")

            # Generate directory tree
            if self.config.pdf_settings.include_tree:
                logger.info("Generating directory tree...")
                tree = self.tree_generator.generate_tree(self.repo_path)
                out_file.write(tree)
                out_file.write("\n\n")

            # Generate code statistics
            if self.config.pdf_settings.include_stats:
                logger.info("Generating code statistics...")
                stats = self.stats_generator.generate_stats(self.repo_path)
                out_file.write(stats)
                out_file.write("\n\n")

            # Process all files
            all_files = self._collect_files()
            logger.info(f"Processing {len(all_files)} files...")

            for file_path in tqdm(
                all_files,
                desc="Processing files",
                unit="file",
                disable=logger.level > logging.INFO,
            ):
                try:
                    content = self._process_single_file(file_path)
                    if content:
                        out_file.write(content)
                        out_file.flush()  # Flush to avoid memory buildup
                except Exception as e:
                    logger.warning(f"Failed to process {file_path}: {e}")
                    # Continue with other files

        # Final scrub: remove any remaining remote images to prevent Pandoc fetching
        try:
            import re

            content = temp_md.read_text(encoding="utf-8")
            # Remove Markdown inline remote images
            content = re.sub(
                r"!\[[^\]]*\]\((https?://[^\s)]+)(\s+\"[^\"]*\")?\)",
                "",
                content,
            )
            # Remove HTML remote images
            content = re.sub(
                r"<img[^>]+src=\"https?://[^\"]+\"[^>]*>", "", content, flags=re.IGNORECASE
            )
            temp_md.write_text(content, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Final remote image scrub failed: {e}")

        return temp_md

    def _collect_files(self) -> list[Path]:
        """
        Collect all files to process from repository.

        Returns:
            List of file paths to process
        """
        all_files = []

        for file_path in sorted(self.repo_path.rglob("*")):
            # Skip directories
            if not file_path.is_file():
                continue

            # Allow special dotfiles like .cursorrules
            if file_path.name in [".cursorrules", ".gitignore", ".env.example"]:
                all_files.append(file_path)
                continue

            # Skip hidden files/directories
            if any(part.startswith(".") for part in file_path.parts):
                continue

            all_files.append(file_path)

        return all_files

    def _process_single_file(self, file_path: Path) -> str:
        """
        Process a single file and return its Markdown representation.

        Args:
            file_path: Path to file

        Returns:
            Markdown content for the file
        """
        ext = file_path.suffix.lower()
        rel_path = file_path.relative_to(self.repo_path)

        # Check if should ignore
        if self.file_processor.should_ignore(file_path):
            return ""

        # Check file size
        try:
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > 0.5 and ext not in IMAGE_EXTENSIONS:
                logger.debug(f"Skipping large file ({file_size_mb:.1f}MB): {file_path}")
                return ""
        except Exception as e:
            logger.warning(f"Failed to get size for {file_path}: {e}")
            return ""

        # Process images
        if ext in IMAGE_EXTENSIONS:
            return self._process_image_file(file_path)

        # Process Markdown files
        if ext in {".md", ".mdx"}:
            return self._process_markdown_file(file_path, rel_path)

        # Process HTML files
        if ext == ".html":
            return self._process_html_file(file_path, rel_path)

        # Process code files
        if ext in CODE_EXTENSIONS:
            return self._process_code_file(file_path, ext, rel_path)

        # Process special files like .cursorrules
        if file_path.name == ".cursorrules":
            return self._process_cursorrules_file(file_path, rel_path)

        return ""

    def _process_image_file(self, file_path: Path) -> str:
        """Process image file (copy to images directory)."""
        import shutil

        ext = file_path.suffix.lower()

        try:
            if ext in {".svg", ".svgz"}:
                # Convert SVG to PNG
                self.image_converter.convert_image_to_png(file_path, self.repo_path)
            else:
                # Copy other images
                target_path = self.images_dir / file_path.name
                shutil.copy2(file_path, target_path)
        except Exception as e:
            logger.warning(f"Failed to process image {file_path}: {e}")

        return ""  # Images are referenced, not included directly

    def _process_markdown_file(self, file_path: Path, rel_path: Path) -> str:
        """Process Markdown file."""
        try:
            content = self.file_processor.read_file_safe(file_path)

            # Process markdown content
            processed = self.markdown_processor.process_markdown_content(
                content, file_path, self.repo_path
            )

            # Escape YAML delimiters
            import re

            processed = re.sub(r"^---$", r"\\---", processed, flags=re.MULTILINE)

            # Return with header
            if file_path.suffix == ".mdx":
                return f"\n\n# {rel_path}\n\n`````mdx\n{processed}\n`````\n\n"
            else:
                return f"\n\n# {rel_path}\n\n{processed}\n\n"

        except Exception as e:
            logger.warning(f"Failed to process Markdown file {file_path}: {e}")
            return ""

    def _process_html_file(self, file_path: Path, rel_path: Path) -> str:
        """Process HTML file (convert to Markdown using Pandoc)."""
        try:
            content = self.file_processor.read_file_safe(file_path)

            result = subprocess.run(
                ["pandoc", "--from=html", "--to=markdown", "--wrap=none"],
                input=content,
                text=True,
                capture_output=True,
                timeout=30,
            )

            if result.returncode == 0:
                return f"\n\n# {rel_path}\n\n{result.stdout}\n\n"

        except Exception as e:
            logger.warning(f"Failed to process HTML file {file_path}: {e}")

        return ""

    def _process_code_file(self, file_path: Path, ext: str, rel_path: Path) -> str:
        """Process code file with syntax highlighting."""
        try:
            content = self.file_processor.read_file_safe(file_path)

            # Skip files containing SVG (likely icon files)
            if self.code_processor.should_skip_file(content):
                return ""

            # Process with code processor
            return self.code_processor.process_code_file(content, ext, str(rel_path))

        except Exception as e:
            logger.warning(f"Failed to process code file {file_path}: {e}")
            return ""

    def _process_cursorrules_file(self, file_path: Path, rel_path: Path) -> str:
        """Process .cursorrules file."""
        try:
            content = self.file_processor.read_file_safe(file_path)
            return f"\n\n# {rel_path}\n\n`````markdown\n{content}\n`````\n\n"
        except Exception as e:
            logger.warning(f"Failed to process .cursorrules file {file_path}: {e}")
            return ""

    def _generate_pdf(self, markdown_file: Path, pandoc_config: Path) -> Path:
        """
        Generate PDF from Markdown using Pandoc.

        Args:
            markdown_file: Path to Markdown file
            pandoc_config: Path to Pandoc defaults file

        Returns:
            Path to generated PDF

        Raises:
            ConversionError: If PDF generation fails
        """
        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_pdf = self.output_dir / f"{self.repo_path.name}_{timestamp}.pdf"

        # Build pandoc command
        cmd = [
            "pandoc",
            str(markdown_file),
            "-o",
            str(output_pdf),
            "--defaults",
            str(pandoc_config),
            "--toc",
            "--toc-depth=2",
            "-V",
            f"title={self.repo_path.name} 代码文档",
            "-V",
            "date=\\today",
        ]

        # Ensure Pandoc can find images referenced relative to the repo root
        # and those generated/copied under temp_dir (current working directory).
        resource_paths = [str(self.temp_dir), str(self.repo_path)]
        cmd.extend(["--resource-path", os.pathsep.join(resource_paths)])

        logger.info(f"Running Pandoc: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600, cwd=self.temp_dir
            )

            if result.returncode != 0:
                logger.error(f"Pandoc stderr: {result.stderr}")
                raise ConversionError("Pandoc conversion failed", details=result.stderr)

            if not output_pdf.exists():
                raise ConversionError("PDF file was not generated")

            return output_pdf

        except subprocess.TimeoutExpired:
            raise ConversionError("Pandoc conversion timed out (>10 minutes)")
        except Exception as e:
            raise ConversionError("Failed to run Pandoc", details=str(e))

    def cleanup(self):
        """Clean up temporary files."""
        try:
            self.latex_generator.clean_temp_files()
            logger.debug("Cleaned up temporary files")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary files: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()
        return False
