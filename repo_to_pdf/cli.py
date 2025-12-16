"""
Command-line interface for repo-to-pdf.

This module provides the CLI entry point with backward compatibility
for the original repo-to-pdf.py script.
"""

import argparse
import logging
import sys
from pathlib import Path

from repo_to_pdf.core.config import AppConfig
from repo_to_pdf.core.exceptions import RepoPDFError


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """
    Configure logging based on verbosity level.

    Args:
        verbose: Enable verbose (DEBUG) logging
        quiet: Enable quiet mode (WARNING+ only)
    """
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Suppress verbose output from third-party libraries
    if not verbose:
        logging.getLogger("git").setLevel(logging.WARNING)
        logging.getLogger("git.cmd").setLevel(logging.WARNING)
        logging.getLogger("git.util").setLevel(logging.WARNING)
        logging.getLogger("MARKDOWN").setLevel(logging.WARNING)


def main() -> int:
    """
    Main CLI entry point.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    parser = argparse.ArgumentParser(
        description="Convert GitHub repository to PDF with syntax highlighting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  repo-to-pdf -c config.yaml

  # With verbose logging
  repo-to-pdf -c config.yaml -v

  # Use specific device preset
  DEVICE=kindle7 repo-to-pdf -c config.yaml

  # Use template
  repo-to-pdf -c config.yaml -t technical

For more information, visit:
  https://github.com/yourusername/githubRepo2Pdf
        """,
    )

    parser.add_argument(
        "-c", "--config", type=Path, required=True, help="Path to configuration YAML file"
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output (DEBUG level)"
    )

    parser.add_argument("-q", "--quiet", action="store_true", help="Only show warnings and errors")

    parser.add_argument(
        "-t",
        "--template",
        type=str,
        default=None,
        help="Template name to use (e.g., default, technical, kindle)",
    )

    parser.add_argument("--version", action="version", version="%(prog)s 2.0.0")

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose, quiet=args.quiet)
    logger = logging.getLogger(__name__)

    # Ensure system dependencies (like Cairo on macOS) are available
    from repo_to_pdf.core.system_utils import ensure_cairo_available

    ensure_cairo_available()

    try:
        # Load configuration
        logger.info(f"Loading configuration from: {args.config}")
        config = AppConfig.from_yaml(args.config)

        # Display configuration summary
        if not args.quiet:
            logger.info("=" * 60)
            logger.info("Repo-to-PDF Converter v2.0.0")
            logger.info("=" * 60)
            logger.info(f"Repository: {config.repository.url}")
            logger.info(f"Branch: {config.repository.branch}")
            logger.info(f"Device Preset: {config.device_preset}")
            if args.template:
                logger.info(f"Template: {args.template}")
            logger.info("=" * 60)

        # Initialize and run converter
        from repo_to_pdf.converter import RepoPDFConverter

        logger.info("🚀 Starting PDF conversion...")
        logger.info("")

        with RepoPDFConverter(config) as converter:
            pdf_path = converter.convert()

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ PDF generated successfully!")
        logger.info(f"📄 Output: {pdf_path}")
        logger.info("=" * 60)

        return 0

    except RepoPDFError as e:
        logger.error(f"❌ {e.message}")
        if e.details and args.verbose:
            logger.error(f"Details: {e.details}")
        return 1

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Operation cancelled by user")
        return 130

    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        if args.verbose:
            logger.exception("Stack trace:")
        return 1


if __name__ == "__main__":
    sys.exit(main())
