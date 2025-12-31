"""Unit tests for claude-code specific Markdown handling."""

from pathlib import Path

import pytest

from repo_to_pdf.converter import RepoPDFConverter
from repo_to_pdf.core.config import AppConfig


@pytest.fixture
def claude_code_config(tmp_path: Path) -> AppConfig:
    config = AppConfig(
        repository={"url": "https://github.com/anthropics/claude-code.git", "branch": "main"},
        workspace_dir=str(tmp_path / "workspace"),
        output_dir=str(tmp_path / "output"),
        pdf_settings={
            "main_font": "Arial",
            "mono_font": "Courier",
            "emoji_download": False,
            "include_hidden_paths": [".claude/**"],
            "raw_markdown_paths": [
                ".claude/**/*.md",
                ".claude/**/*.mdx",
                "plugins/**/*.md",
                "plugins/**/*.mdx",
            ],
            "raw_markdown_exclude_paths": ["**/README.md"],
        },
        ignores=["node_modules", "*.pyc", ".git"],
    )
    config._project_root = tmp_path
    return config


@pytest.fixture
def claude_code_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "claude-code"
    (repo / ".claude").mkdir(parents=True)
    (repo / "plugins").mkdir(parents=True)

    (repo / ".claude" / "README.md").write_text("# .claude README\n", encoding="utf-8")
    (repo / ".claude" / "prompt.md").write_text("Prompt: `{{var}}`\n", encoding="utf-8")
    (repo / "plugins" / "README.md").write_text("# Plugins README\n", encoding="utf-8")
    (repo / "plugins" / "example.md").write_text("Some *markdown*.\n", encoding="utf-8")

    return repo


class TestClaudeCodeRawMarkdown:
    def test_collect_files_includes_dot_claude(
        self, claude_code_config: AppConfig, claude_code_repo: Path
    ):
        converter = RepoPDFConverter(claude_code_config)
        converter.repo_path = claude_code_repo

        files = converter._collect_files()
        rels = {str(p.relative_to(claude_code_repo)) for p in files}

        assert ".claude/prompt.md" in rels
        assert "plugins/example.md" in rels

    def test_markdown_under_dot_claude_is_raw_except_readme(
        self, claude_code_config: AppConfig, claude_code_repo: Path
    ):
        converter = RepoPDFConverter(claude_code_config)
        converter.repo_path = claude_code_repo

        raw_file = claude_code_repo / ".claude" / "prompt.md"
        readme_file = claude_code_repo / ".claude" / "README.md"

        raw_out = converter._process_markdown_file(raw_file, raw_file.relative_to(claude_code_repo))
        readme_out = converter._process_markdown_file(
            readme_file, readme_file.relative_to(claude_code_repo)
        )

        assert "`````" in raw_out
        assert "Prompt: `{{var}}`" in raw_out
        assert "`````" not in readme_out
        assert "# .claude README" in readme_out

    def test_markdown_under_plugins_is_raw_except_readme(
        self, claude_code_config: AppConfig, claude_code_repo: Path
    ):
        converter = RepoPDFConverter(claude_code_config)
        converter.repo_path = claude_code_repo

        raw_file = claude_code_repo / "plugins" / "example.md"
        readme_file = claude_code_repo / "plugins" / "README.md"

        raw_out = converter._process_markdown_file(raw_file, raw_file.relative_to(claude_code_repo))
        readme_out = converter._process_markdown_file(
            readme_file, readme_file.relative_to(claude_code_repo)
        )

        assert "`````" in raw_out
        assert "Some *markdown*." in raw_out
        assert "`````" not in readme_out
        assert "# Plugins README" in readme_out
