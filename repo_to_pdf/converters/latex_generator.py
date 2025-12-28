"""LaTeX header and pandoc configuration generation."""

import logging
import platform
from pathlib import Path
from typing import Dict, List

from repo_to_pdf.core.config import AppConfig

logger = logging.getLogger(__name__)


def get_system_fonts() -> Dict[str, str]:
    """
    Detect system fonts based on platform.

    Returns:
        Dictionary with font names for main_font, sans_font, mono_font, and emoji_fonts
    """
    system = platform.system()

    if system == "Darwin":  # macOS
        return {
            "main_font": "Songti SC",
            "sans_font": "Heiti SC",
            "mono_font": "SF Mono",
            "emoji_fonts": ["Apple Color Emoji"],
        }
    else:  # Linux/WSL
        # Prefer widely available fonts; avoid Symbola to prevent TeX fallback issues
        return {
            "main_font": "Noto Serif CJK SC",
            "sans_font": "Noto Sans CJK SC",
            "mono_font": "DejaVu Sans Mono",
            "emoji_fonts": ["Noto Color Emoji"],
        }


class LaTeXGenerator:
    """Generates LaTeX headers and pandoc configuration."""

    def __init__(self, config: AppConfig, output_dir: Path):
        """
        Initialize the LaTeX generator.

        Args:
            config: Application configuration
            output_dir: Directory where LaTeX files will be written
        """
        self.config = config
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_pandoc_config(self, repo_name: str) -> Path:
        """
        Generate pandoc defaults YAML configuration.

        Args:
            repo_name: Repository name for PDF title

        Returns:
            Path to generated pandoc defaults file
        """
        # Get system fonts
        system_fonts = get_system_fonts()

        # Get fonts from config, fallback to system fonts
        main_font = self.config.pdf_settings.main_font or system_fonts["main_font"]
        sans_font = self.config.pdf_settings.sans_font or system_fonts["sans_font"]
        mono_font = self.config.pdf_settings.mono_font or system_fonts["mono_font"]

        # Get PDF settings
        margin = self.config.pdf_settings.margin
        highlight_style = self.config.pdf_settings.highlight_style

        # Generate header.tex file first
        header_tex_path = self.generate_latex_header(
            repo_name, main_font, sans_font, mono_font, system_fonts
        )

        # Create pandoc defaults YAML
        yaml_content = f"""# Pandoc defaults file
pdf-engine: xelatex
from: markdown+fenced_code_attributes+fenced_code_blocks+backtick_code_blocks-yaml_metadata_block-tex_math_dollars-raw_tex
highlight-style: {highlight_style}

include-in-header:
  - {header_tex_path}

variables:
  documentclass: article
  geometry: {margin}
  CJKmainfont: "{main_font}"
  CJKsansfont: "{sans_font}"
  CJKmonofont: "{main_font}"
  monofont: "{mono_font}"
  monofontoptions:
    - Scale=0.85
  colorlinks: true
  linkcolor: blue
  urlcolor: blue
"""

        yaml_path = self.output_dir / "pandoc_defaults.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")

        logger.info(f"Generated pandoc config: {yaml_path}")
        return yaml_path

    def generate_latex_header(
        self,
        repo_name: str,
        main_font: str,
        sans_font: str,
        mono_font: str,
        system_fonts: Dict[str, str],
    ) -> Path:
        """
        Generate LaTeX header file (header.tex).

        Args:
            repo_name: Repository name for PDF title
            main_font: Main document font
            sans_font: Sans-serif font
            mono_font: Monospace font
            system_fonts: System fonts dictionary

        Returns:
            Path to generated header.tex file
        """
        # Get emoji font candidates
        emoji_candidates = self._get_emoji_font_candidates(system_fonts)

        # Generate emoji font fallback setup
        emoji_setup_tex = self._generate_emoji_fallback_setup(emoji_candidates, mono_font)

        # Get PDF settings
        code_fontsize = self.config.pdf_settings.code_fontsize
        linespread = self.config.pdf_settings.linespread
        parskip = self.config.pdf_settings.parskip

        # Get code block visual settings
        code_bg = self.config.pdf_settings.code_block_bg
        code_border = self.config.pdf_settings.code_block_border
        code_padding = self.config.pdf_settings.code_block_padding

        # Build header content
        header_content = f"""% LaTeX header for repo-to-pdf
% Generated automatically - do not edit manually

% ============================================================================
% Package imports
% ============================================================================
\\usepackage{{fontspec}}
\\usepackage{{xunicode}}
\\usepackage{{xeCJK}}
\\usepackage{{fvextra}}
\\usepackage{{xstring}}
\\usepackage[most]{{tcolorbox}}
\\usepackage{{graphicx}}
\\usepackage{{float}}
\\usepackage{{sectsty}}
\\usepackage{{hyperref}}
\\usepackage{{longtable}}
\\usepackage{{ragged2e}}
\\usepackage{{listings}}
\\usepackage{{adjustbox}}

% ============================================================================
% Document settings
% ============================================================================
\\AtBeginDocument{{\\justifying}}
\\hypersetup{{pdftitle={{{repo_name} 代码文档}}, pdfauthor={{Repo-to-PDF Generator}}, colorlinks=true, linkcolor=blue, urlcolor=blue}}

% ============================================================================
% Layout settings
% ============================================================================
\\linespread{{{linespread}}}
\\setlength{{\\parskip}}{{{parskip}}}

% ============================================================================
% Font settings
% ============================================================================
\\defaultfontfeatures{{Mapping=tex-text}}
\\setCJKmainfont{{{main_font}}}
\\setCJKsansfont{{{sans_font}}}
\\setCJKmonofont{{{main_font}}}

% Chinese line breaking
\\XeTeXlinebreaklocale "zh"
\\XeTeXlinebreakskip = 0pt plus 1pt

% Section title fonts
\\allsectionsfont{{\\CJKfamily{{sf}}}}

% ============================================================================
% Graphics settings
% ============================================================================
\\DeclareGraphicsExtensions{{.png,.jpg,.jpeg,.gif}}
\\graphicspath{{{{./images/}}}}
\\setkeys{{Gin}}{{width=0.8\\linewidth,keepaspectratio}}

% ============================================================================
% Code block settings
% ============================================================================
\\RecustomVerbatimEnvironment{{verbatim}}{{Verbatim}}{{breaklines}}
\\DefineVerbatimEnvironment{{Highlighting}}{{Verbatim}}{{breaklines,commandchars=\\\\\\{{\\}}, fontsize={code_fontsize}}}
\\fvset{{breaklines=true, breakanywhere=true, breakafter=\\\\, fontsize={code_fontsize}}}

% Shaded code block environment with enhanced styling
\\renewenvironment{{Shaded}}{{%
    \\begin{{tcolorbox}}[
        breakable,
        enhanced,
        boxrule=0.5pt,
        colback={code_bg},
        colframe={code_border},
        arc=2pt,
        boxsep={code_padding},
        left=3pt,
        right=3pt,
        top=3pt,
        bottom=3pt,
        sharp corners=south
    ]%
}}{{\\end{{tcolorbox}}}}

% ============================================================================
% Emoji support
% ============================================================================
% Emoji image macro (for inserting PNG in code blocks)
% Be tolerant if the argument omits the .png suffix
\\newcommand{{\\emojiimg}}[1]{{%
  \\begingroup
  \\def\\emfilename{{#1}}%
  \\IfEndWith{{\\emfilename}}{{.png}}{{%
    \\raisebox{{-0.2ex}}{{\\includegraphics[height=1.0em]{{images/emoji/#1}}}}%
  }}{{%
    \\raisebox{{-0.2ex}}{{\\includegraphics[height=1.0em]{{images/emoji/#1.png}}}}%
  }}%
  \\endgroup
}}

% Emoji font fallback setup
{emoji_setup_tex}

% ============================================================================
% CodeBlock environment (for emoji in code)
% ============================================================================
% This environment allows emoji images in code blocks using special syntax
% Usage: §emojiimg«filename.png»
\\usepackage{{etoolbox}}
\\makeatletter
\\newenvironment{{CodeBlock}}{{%
    \\VerbatimEnvironment
    \\begin{{Verbatim}}[commandchars=§«»,fontsize={code_fontsize},breakanywhere=false]%
}}{{%
    \\end{{Verbatim}}%
}}
\\makeatother

% ============================================================================
% LaTeX overflow prevention
% ============================================================================
\\maxdeadcycles=200
\\emergencystretch=5em
"""

        header_path = self.output_dir / "header.tex"
        header_path.write_text(header_content, encoding="utf-8")

        logger.info(f"Generated LaTeX header: {header_path}")
        return header_path

    def _get_emoji_font_candidates(self, system_fonts: Dict[str, str]) -> List[str]:
        """
        Get list of emoji font candidates.

        Combines config emoji fonts with system emoji fonts.

        Args:
            system_fonts: System fonts dictionary

        Returns:
            List of emoji font names to try
        """
        emoji_candidates = []

        # Add fonts from config
        cfg_emoji = self.config.pdf_settings.emoji_font
        if isinstance(cfg_emoji, list):
            emoji_candidates.extend([str(x) for x in cfg_emoji if x])
        elif isinstance(cfg_emoji, str) and cfg_emoji.strip():
            emoji_candidates.append(cfg_emoji.strip())

        # Add system emoji fonts
        for font in system_fonts.get("emoji_fonts", []):
            if font not in emoji_candidates:
                emoji_candidates.append(font)

        return emoji_candidates

    def _generate_emoji_fallback_setup(self, emoji_candidates: List[str], mono_font: str) -> str:
        """
        Generate LaTeX code for emoji font fallback.

        Tries each emoji font candidate and sets up fallback.

        Args:
            emoji_candidates: List of emoji font names
            mono_font: Monospace font name

        Returns:
            LaTeX code for emoji fallback setup
        """
        lines = [
            "% Emoji font fallback setup",
            "\\newif\\ifemojiavailable",
            "\\emojiavailablefalse",
        ]

        # Try each candidate font
        for font_name in emoji_candidates:
            # Sanitize font name for LaTeX
            safe_name = font_name.replace("\\\\", r"\\\\").replace("{", "").replace("}", "")
            lines.append(
                f"\\IfFontExistsTF{{{safe_name}}}{{\\newfontfamily\\EmojiFont{{{safe_name}}}\\emojiavailabletrue}}{{}}"
            )

        # Set monofont with or without emoji fallback
        lines.append(
            f"\\ifemojiavailable\\setmonofont[Scale=0.85,FallbackFamilies={{{{EmojiFont}}}}]{{{mono_font}}}\\else\\setmonofont[Scale=0.85]{{{mono_font}}}\\fi"
        )

        return "\n".join(lines)

    def create_metadata_yaml(self, repo_name: str, author: str = "Repo-to-PDF") -> Path:
        """
        Create YAML metadata file for pandoc.

        Args:
            repo_name: Repository name
            author: Author name

        Returns:
            Path to metadata YAML file
        """
        metadata = f"""---
title: "{repo_name} 代码文档"
author: "{author}"
date: "{self._get_current_date()}"
---
"""

        metadata_path = self.output_dir / "metadata.yaml"
        metadata_path.write_text(metadata, encoding="utf-8")

        return metadata_path

    def _get_current_date(self) -> str:
        """Get current date in YYYY-MM-DD format."""
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d")

    def clean_temp_files(self) -> None:
        """Remove generated temporary LaTeX files."""
        temp_files = ["header.tex", "pandoc_defaults.yaml", "metadata.yaml"]

        for filename in temp_files:
            filepath = self.output_dir / filename
            if filepath.exists():
                filepath.unlink()
                logger.debug(f"Removed temp file: {filepath}")
