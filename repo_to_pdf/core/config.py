"""
Configuration management with Pydantic validation.

This module provides strongly-typed configuration models with validation
for all application settings.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from repo_to_pdf.core.constants import (
    CODE_FONTSIZE_OPTIONS,
    DEFAULT_CODE_FONTSIZE,
    DEFAULT_FONTSIZE,
    DEFAULT_IGNORE_PATTERNS,
    DEFAULT_LINESPREAD,
    DEFAULT_MARGIN,
    DEFAULT_PARSKIP,
    DEVICE_PRESETS,
    PANDOC_HIGHLIGHT_STYLE,
    VALID_FONTSIZES,
)
from repo_to_pdf.core.exceptions import ConfigurationError


class RepositoryConfig(BaseModel):
    """
    Repository configuration.

    Attributes:
        url: Git repository URL (HTTP/HTTPS or SSH)
        branch: Branch name to checkout (default: "main")

    Example:
        >>> repo = RepositoryConfig(
        ...     url="https://github.com/user/repo.git",
        ...     branch="main"
        ... )
    """

    url: str = Field(..., description="Git repository URL")
    branch: str = Field(default="main", description="Branch to checkout")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate repository URL format."""
        v = v.strip()
        if not v:
            raise ValueError("Repository URL cannot be empty")

        # Check for valid URL schemes
        valid_schemes = ["http://", "https://", "git@", "ssh://"]
        if not any(v.startswith(scheme) for scheme in valid_schemes):
            raise ValueError(f"Repository URL must start with one of: {', '.join(valid_schemes)}")

        return v

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: str) -> str:
        """Validate branch name."""
        v = v.strip()
        if not v:
            raise ValueError("Branch name cannot be empty")
        return v


class PDFSettings(BaseModel):
    """
    PDF generation settings.

    Attributes:
        margin: Page margins (e.g., "margin=1in")
        main_font: Main document font
        mono_font: Monospace font for code
        emoji_font: Emoji font (string or list of fallbacks)
        fontsize: Document font size
        code_fontsize: Code block font size
        linespread: Line spacing multiplier
        parskip: Paragraph spacing
        highlight_style: Pandoc syntax highlighting style
        split_large_files: Whether to split large files
        render_header_comments_outside_code: Extract header comments as text
        code_block_strategy: Code block rendering strategy
        emoji_download: Allow downloading emoji from CDN
        max_line_length: Maximum line length before hard wrapping
    """

    margin: str = Field(default=DEFAULT_MARGIN, description="Page margins")
    main_font: str = Field(..., description="Main document font")
    mono_font: str = Field(..., description="Monospace font for code")
    emoji_font: Optional[Union[str, List[str]]] = Field(
        default=None, description="Emoji font or list of fallback fonts"
    )
    fontsize: str = Field(default=DEFAULT_FONTSIZE, description="Document font size")
    code_fontsize: str = Field(default=DEFAULT_CODE_FONTSIZE, description="Code block font size")
    linespread: str = Field(default=DEFAULT_LINESPREAD, description="Line spacing")
    parskip: str = Field(default=DEFAULT_PARSKIP, description="Paragraph spacing")
    highlight_style: str = Field(
        default=PANDOC_HIGHLIGHT_STYLE, description="Syntax highlighting style"
    )
    split_large_files: bool = Field(
        default=True, description="Split large files into multiple parts"
    )
    render_header_comments_outside_code: bool = Field(
        default=True, description="Render header comments as text (not code)"
    )
    code_block_strategy: str = Field(
        default="normal", description="Code block strategy: normal or codeblock_for_emoji"
    )
    emoji_download: bool = Field(default=True, description="Allow downloading emoji from CDN")
    max_line_length: int = Field(
        default=200, ge=40, le=500, description="Maximum line length before hard wrapping"
    )

    # Markdown rendering controls
    include_hidden_paths: List[str] = Field(
        default_factory=list,
        description=(
            "Repo-relative glob patterns to include files under hidden paths "
            "(e.g., ['.claude/**'])."
        ),
    )
    raw_markdown_paths: List[str] = Field(
        default_factory=list,
        description=(
            "Repo-relative glob patterns for Markdown files to render as fenced code blocks "
            "without Markdown parsing (e.g., ['.claude/**/*.md', 'plugins/**/*.md'])."
        ),
    )
    raw_markdown_exclude_paths: List[str] = Field(
        default_factory=lambda: ["**/README.md"],
        description="Repo-relative glob patterns excluded from raw_markdown_paths.",
    )

    # Code block visual enhancement settings
    code_block_bg: str = Field(
        default="gray!5",
        description="Code block background color (LaTeX color spec, e.g., 'gray!5', 'blue!3')",
    )
    code_block_border: str = Field(
        default="gray!30",
        description="Code block border color (LaTeX color spec, e.g., 'gray!30', 'blue!20')",
    )
    code_block_padding: str = Field(
        default="5pt", description="Code block padding (LaTeX dimension, e.g., '5pt', '3mm')"
    )

    include_tree: bool = Field(default=True, description="Include directory tree in output")
    include_stats: bool = Field(default=True, description="Include code statistics in output")
    tree_max_depth: int = Field(
        default=3, ge=1, le=10, description="Maximum depth for directory tree"
    )
    sans_font: Optional[str] = Field(
        default=None, description="Sans-serif font (auto-detected if not set)"
    )
    metadata: Dict[str, str] = Field(
        default_factory=lambda: {
            "author": "Repo-to-PDF Generator",
            "creator": "LaTeX",
            "producer": "XeLaTeX",
        },
        description="PDF metadata",
    )

    @field_validator("fontsize")
    @classmethod
    def validate_fontsize(cls, v: str) -> str:
        """Validate font size."""
        if v not in VALID_FONTSIZES:
            raise ValueError(f"fontsize must be one of: {', '.join(sorted(VALID_FONTSIZES))}")
        return v

    @field_validator("code_fontsize")
    @classmethod
    def validate_code_fontsize(cls, v: str) -> str:
        """Validate code font size."""
        # Allow LaTeX commands or named sizes
        if v.startswith("\\"):
            return v
        if v in CODE_FONTSIZE_OPTIONS:
            return CODE_FONTSIZE_OPTIONS[v]
        # If it's already a LaTeX command, allow it
        if v in CODE_FONTSIZE_OPTIONS.values():
            return v
        raise ValueError(
            f"code_fontsize must be one of: {', '.join(CODE_FONTSIZE_OPTIONS.keys())} "
            f"or a LaTeX size command like \\small"
        )

    @field_validator("code_block_strategy")
    @classmethod
    def validate_code_block_strategy(cls, v: str) -> str:
        """Validate code block strategy."""
        valid_strategies = ["normal", "codeblock_for_emoji"]
        if v not in valid_strategies:
            raise ValueError(f"code_block_strategy must be one of: {', '.join(valid_strategies)}")
        return v


class DevicePreset(BaseModel):
    """
    Device-specific preset configuration.

    Attributes:
        description: Human-readable description
        template: Template name to use
        pdf_overrides: PDF settings to override
    """

    description: str = Field(..., description="Preset description")
    template: str = Field(default="default", description="Template name")
    pdf_overrides: Dict[str, Any] = Field(
        default_factory=dict, description="PDF settings overrides"
    )


class AppConfig(BaseModel):
    """
    Main application configuration.

    Attributes:
        repository: Repository configuration
        workspace_dir: Directory for cloned repositories
        output_dir: Directory for generated PDFs
        pdf_settings: PDF generation settings
        ignores: Patterns for files/directories to ignore
        device_preset: Active device preset name
        device_presets: Available device presets

    Example:
        >>> config = AppConfig.from_yaml("config.yaml")
        >>> converter = RepoPDFConverter(config)
    """

    repository: RepositoryConfig = Field(..., description="Repository configuration")
    workspace_dir: str = Field(default="./repo-workspace", description="Workspace directory")
    output_dir: str = Field(default="./repo-pdfs", description="Output directory")
    pdf_settings: PDFSettings = Field(..., description="PDF settings")
    ignores: List[str] = Field(
        default_factory=lambda: list(DEFAULT_IGNORE_PATTERNS), description="Ignore patterns"
    )
    device_preset: str = Field(default="desktop", description="Active device preset")
    device_presets: Dict[str, DevicePreset] = Field(
        default_factory=dict, description="Device presets"
    )

    # Internal fields
    _project_root: Optional[Path] = None
    _applied_preset: bool = False

    @classmethod
    def from_yaml(cls, config_path: Union[str, Path]) -> "AppConfig":
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to configuration YAML file

        Returns:
            Validated AppConfig instance

        Raises:
            ConfigurationError: If config file is invalid

        Example:
            >>> config = AppConfig.from_yaml("config.yaml")
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigurationError("Invalid YAML syntax in configuration file", str(e))
        except Exception as e:
            raise ConfigurationError(f"Failed to read configuration file: {config_path}", str(e))

        if not data:
            raise ConfigurationError("Configuration file is empty")

        # Store project root
        project_root = config_path.parent.absolute()

        # Create config instance
        try:
            config = cls(**data)
            config._project_root = project_root
            return config
        except Exception as e:
            raise ConfigurationError("Invalid configuration", str(e))

    @model_validator(mode="after")
    def apply_device_preset(self) -> "AppConfig":
        """Apply device preset if specified and not already applied."""
        if self._applied_preset:
            return self

        # Get device preset from environment or config
        preset_name = os.environ.get("DEVICE") or self.device_preset

        # Merge built-in presets with user-defined presets
        all_presets = {**DEVICE_PRESETS, **self.device_presets}

        if preset_name and preset_name in all_presets:
            preset_data = all_presets[preset_name]

            # Convert dict to DevicePreset if needed
            if isinstance(preset_data, dict):
                preset = DevicePreset(**preset_data)
            else:
                preset = preset_data

            # Apply PDF overrides
            if preset.pdf_overrides:
                for key, value in preset.pdf_overrides.items():
                    if hasattr(self.pdf_settings, key):
                        setattr(self.pdf_settings, key, value)

            self._applied_preset = True

        return self

    @property
    def project_root(self) -> Path:
        """Get project root directory."""
        if self._project_root is None:
            return Path.cwd()
        return self._project_root

    @property
    def workspace_path(self) -> Path:
        """Get absolute workspace directory path."""
        workspace = Path(self.workspace_dir)
        if not workspace.is_absolute():
            workspace = self.project_root / workspace
        return workspace

    @property
    def output_path(self) -> Path:
        """Get absolute output directory path."""
        output = Path(self.output_dir)
        if not output.is_absolute():
            output = self.project_root / output
        return output

    def to_yaml(self, output_path: Union[str, Path]) -> None:
        """
        Save configuration to YAML file.

        Args:
            output_path: Path to save configuration

        Example:
            >>> config.to_yaml("config_backup.yaml")
        """
        output_path = Path(output_path)

        # Convert to dict
        data = self.model_dump(exclude={"_project_root", "_applied_preset"})

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            raise ConfigurationError(f"Failed to write configuration to {output_path}", str(e))

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True
        validate_assignment = True
