"""Unit tests for file processor."""

from pathlib import Path

import pytest

from repo_to_pdf.core.config import AppConfig
from repo_to_pdf.core.exceptions import FileProcessingError, ValidationError
from repo_to_pdf.processors.file_processor import FileProcessor


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing."""
    config_dict = {
        "repository": {"url": "https://github.com/test/repo.git", "branch": "main"},
        "workspace_dir": "./workspace",
        "output_dir": "./output",
        "pdf_settings": {"main_font": "Arial", "mono_font": "Courier"},
        "ignores": ["node_modules", "*.pyc", ".git"],
    }
    return AppConfig(**config_dict)


@pytest.fixture
def file_processor(sample_config):
    """Create FileProcessor instance."""
    return FileProcessor(sample_config)


class TestIgnoreLogic:
    """Test file ignore logic."""

    def test_should_ignore_exact_match(self, file_processor):
        """Test exact directory match."""
        path = Path("project/node_modules/package.json")
        assert file_processor.should_ignore(path) is True

    def test_should_ignore_wildcard(self, file_processor):
        """Test wildcard pattern matching."""
        path = Path("project/test.pyc")
        assert file_processor.should_ignore(path) is True

    def test_should_not_ignore_valid_file(self, file_processor):
        """Test that valid files are not ignored."""
        path = Path("src/main.py")
        assert file_processor.should_ignore(path) is False

    def test_should_ignore_binary_extension(self, file_processor):
        """Test that binary files are ignored."""
        path = Path("compiled.so")
        assert file_processor.should_ignore(path) is True


class TestPathSafety:
    """Test path safety validation."""

    def test_safe_path(self, file_processor):
        """Test that safe paths pass validation."""
        base = Path("/home/user/repo")
        safe = Path("/home/user/repo/src/file.py")
        assert file_processor.is_safe_path(base, safe) is True

    def test_unsafe_path_traversal(self, file_processor):
        """Test that path traversal is detected."""
        base = Path("/home/user/repo")
        unsafe = Path("/home/user/repo/../../../etc/passwd")
        assert file_processor.is_safe_path(base, unsafe) is False

    def test_sibling_directory(self, file_processor):
        """Test that sibling directories are rejected."""
        base = Path("/home/user/repo")
        sibling = Path("/home/user/other/file.txt")
        assert file_processor.is_safe_path(base, sibling) is False


class TestFileReading:
    """Test file reading operations."""

    def test_read_small_file(self, file_processor, tmp_path):
        """Test reading a small file."""
        test_file = tmp_path / "test.txt"
        test_content = "Hello, World!"
        test_file.write_text(test_content)

        content = file_processor.read_file_safe(test_file)
        assert content == test_content

    def test_read_large_file_fails(self, file_processor, tmp_path):
        """Test that large files are rejected."""
        test_file = tmp_path / "large.txt"
        # Create file larger than default limit
        large_content = "x" * (1024 * 1024 + 1)  # > 0.5MB
        test_file.write_text(large_content)

        with pytest.raises(ValidationError):
            file_processor.read_file_safe(test_file)

    def test_read_nonexistent_file(self, file_processor):
        """Test reading non-existent file raises error."""
        with pytest.raises(FileProcessingError):
            file_processor.read_file_safe(Path("/nonexistent/file.txt"))

    def test_read_file_lines(self, file_processor, tmp_path):
        """Test reading file line by line."""
        test_file = tmp_path / "lines.txt"
        lines = ["Line 1\n", "Line 2\n", "Line 3\n"]
        test_file.write_text("".join(lines))

        read_lines = list(file_processor.read_file_lines(test_file))
        assert read_lines == lines


class TestFileCollection:
    """Test file collection."""

    def test_collect_files_basic(self, file_processor, tmp_path):
        """Test collecting files from directory."""
        # Create test structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "README.md").write_text("# Test")

        files = file_processor.collect_files(tmp_path)

        assert len(files) == 2
        assert any(f.name == "main.py" for f in files)
        assert any(f.name == "README.md" for f in files)

    def test_collect_files_excludes_ignored(self, file_processor, tmp_path):
        """Test that ignored files are excluded."""
        # Create test structure with ignored files
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "package.json").write_text("{}")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")

        files = file_processor.collect_files(tmp_path)

        # Should not include node_modules files
        assert not any("node_modules" in str(f) for f in files)
        assert any(f.name == "main.py" for f in files)

    def test_collect_files_excludes_hidden(self, file_processor, tmp_path):
        """Test that hidden files are excluded by default."""
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / "visible.txt").write_text("public")

        files = file_processor.collect_files(tmp_path, include_hidden=False)

        assert not any(f.name == ".hidden" for f in files)
        assert any(f.name == "visible.txt" for f in files)


class TestFileTypeDetection:
    """Test file type detection."""

    def test_is_text_file_python(self, file_processor, tmp_path):
        """Test Python file is detected as text."""
        test_file = tmp_path / "script.py"
        test_file.write_text("print('hello')")

        assert file_processor.is_text_file(test_file) is True

    def test_is_text_file_binary(self, file_processor, tmp_path):
        """Test binary file is detected."""
        test_file = tmp_path / "binary.so"
        test_file.write_bytes(b"\x00\x01\x02\x03")

        assert file_processor.is_text_file(test_file) is False


class TestFileInfo:
    """Test file info retrieval."""

    def test_get_file_info(self, file_processor, tmp_path):
        """Test getting file metadata."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        info = file_processor.get_file_info(test_file)

        assert info["name"] == "test.py"
        assert info["extension"] == ".py"
        assert info["size_bytes"] > 0
        assert "modified" in info
