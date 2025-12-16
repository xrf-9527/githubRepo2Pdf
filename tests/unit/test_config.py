"""Unit tests for configuration module."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from repo_to_pdf.core.config import (
    AppConfig,
    DevicePreset,
    PDFSettings,
    RepositoryConfig,
)


class TestRepositoryConfig:
    """Test RepositoryConfig model."""

    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        config = RepositoryConfig(url="https://github.com/user/repo.git", branch="main")
        assert config.url == "https://github.com/user/repo.git"
        assert config.branch == "main"

    def test_valid_ssh_url(self):
        """Test valid SSH URL."""
        config = RepositoryConfig(url="git@github.com:user/repo.git", branch="develop")
        assert config.url == "git@github.com:user/repo.git"

    def test_empty_url_raises_error(self):
        """Test that empty URL raises ValidationError."""
        with pytest.raises(ValidationError):
            RepositoryConfig(url="", branch="main")

    def test_invalid_url_raises_error(self):
        """Test that invalid URL raises ValidationError."""
        with pytest.raises(ValidationError):
            RepositoryConfig(url="not-a-valid-url", branch="main")

    def test_default_branch(self):
        """Test default branch is 'main'."""
        config = RepositoryConfig(url="https://github.com/user/repo.git")
        assert config.branch == "main"


class TestPDFSettings:
    """Test PDFSettings model."""

    def test_valid_fontsize(self):
        """Test valid font size."""
        settings = PDFSettings(main_font="Arial", mono_font="Courier", fontsize="10pt")
        assert settings.fontsize == "10pt"

    def test_invalid_fontsize_raises_error(self):
        """Test invalid font size raises ValidationError."""
        with pytest.raises(ValidationError):
            PDFSettings(main_font="Arial", mono_font="Courier", fontsize="invalid")

    def test_valid_code_fontsize(self):
        """Test valid code font sizes."""
        valid_sizes = [r"\tiny", r"\small", r"\normalsize", "small", "tiny"]

        for size in valid_sizes:
            PDFSettings(main_font="Arial", mono_font="Courier", code_fontsize=size)
            # Should not raise

    def test_max_line_length_range(self):
        """Test max_line_length validation."""
        # Valid range
        settings = PDFSettings(main_font="Arial", mono_font="Courier", max_line_length=100)
        assert settings.max_line_length == 100

        # Too small
        with pytest.raises(ValidationError):
            PDFSettings(main_font="Arial", mono_font="Courier", max_line_length=10)  # < 40

    def test_default_values(self):
        """Test default values."""
        settings = PDFSettings(main_font="Arial", mono_font="Courier")
        assert settings.split_large_files is True
        assert settings.emoji_download is True
        assert settings.render_header_comments_outside_code is True


class TestAppConfig:
    """Test AppConfig model."""

    @pytest.fixture
    def sample_config_dict(self):
        """Sample configuration dictionary."""
        return {
            "repository": {"url": "https://github.com/user/repo.git", "branch": "main"},
            "workspace_dir": "./workspace",
            "output_dir": "./output",
            "pdf_settings": {"main_font": "Arial", "mono_font": "Courier", "fontsize": "10pt"},
            "ignores": ["node_modules", "*.pyc"],
            "device_preset": "desktop",
        }

    def test_create_from_dict(self, sample_config_dict):
        """Test creating AppConfig from dict."""
        config = AppConfig(**sample_config_dict)

        assert config.repository.url == "https://github.com/user/repo.git"
        assert config.pdf_settings.fontsize == "10pt"
        assert "node_modules" in config.ignores

    def test_device_preset_application(self, sample_config_dict):
        """Test device preset is applied."""
        sample_config_dict["device_preset"] = "kindle7"
        config = AppConfig(**sample_config_dict)

        # Kindle preset should override fontsize to 11pt
        assert config.pdf_settings.fontsize == "11pt"
        assert config.pdf_settings.margin == "margin=0.4in"

    def test_project_root_property(self, sample_config_dict):
        """Test project_root property."""
        config = AppConfig(**sample_config_dict)
        assert isinstance(config.project_root, Path)

    def test_workspace_path_property(self, sample_config_dict):
        """Test workspace_path resolves to absolute path."""
        config = AppConfig(**sample_config_dict)
        assert config.workspace_path.is_absolute()

    def test_output_path_property(self, sample_config_dict):
        """Test output_path resolves to absolute path."""
        config = AppConfig(**sample_config_dict)
        assert config.output_path.is_absolute()


class TestDevicePreset:
    """Test DevicePreset model."""

    def test_create_preset(self):
        """Test creating device preset."""
        preset = DevicePreset(
            description="Test preset", template="default", pdf_overrides={"fontsize": "12pt"}
        )

        assert preset.description == "Test preset"
        assert preset.template == "default"
        assert preset.pdf_overrides["fontsize"] == "12pt"

    def test_default_template(self):
        """Test default template value."""
        preset = DevicePreset(description="Test preset")
        assert preset.template == "default"
