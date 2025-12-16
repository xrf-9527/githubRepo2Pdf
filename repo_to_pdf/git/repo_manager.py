"""
Git repository management module.

This module handles Git operations including cloning, pulling, and updating
repositories with proper error handling and resource management.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import git

from repo_to_pdf.core.exceptions import GitOperationError

logger = logging.getLogger(__name__)


class GitRepoManager:
    """
    Manages Git repository operations.

    This class provides context manager support for automatic cleanup,
    handles both HTTP(S) and SSH URLs, and implements shallow cloning
    for better performance.

    Attributes:
        repo_url: Git repository URL
        branch: Branch name to checkout
        repo_dir: Path to cloned repository
        _cleanup_on_exit: Whether to cleanup on exit

    Example:
        >>> manager = GitRepoManager(
        ...     "https://github.com/user/repo.git",
        ...     branch="main"
        ... )
        >>> repo_path = manager.clone_or_pull(workspace_dir)
        >>> # ... process files
        >>> manager.cleanup()  # Manual cleanup

        # Or use as context manager for automatic cleanup:
        >>> with GitRepoManager(url, branch) as manager:
        ...     repo_path = manager.clone_or_pull(workspace)
        ...     # ... process files
        # Automatic cleanup on exit
    """

    def __init__(self, repo_url: str, branch: str = "main", cleanup_on_exit: bool = False):
        """
        Initialize Git repository manager.

        Args:
            repo_url: Git repository URL (HTTP/HTTPS or SSH)
            branch: Branch to checkout (default: "main")
            cleanup_on_exit: Whether to cleanup repository on exit

        Raises:
            GitOperationError: If URL is invalid
        """
        self.repo_url = repo_url.strip()
        self.branch = branch.strip()
        self.repo_dir: Optional[Path] = None
        self._cleanup_on_exit = cleanup_on_exit
        self._repo_name = self._extract_repo_name(repo_url)

        # Set Git environment variables for better performance
        if os.uname().sysname == "Darwin":  # macOS
            os.environ["GIT_PYTHON_GIT_EXECUTABLE"] = "/usr/bin/git"
            os.environ["GIT_PYTHON_REFRESH"] = "quiet"

        # Suppress Git module logging
        logging.getLogger("git").setLevel(logging.WARNING)
        logging.getLogger("git.cmd").setLevel(logging.WARNING)

    def __enter__(self) -> "GitRepoManager":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit with automatic cleanup."""
        if self._cleanup_on_exit:
            self.cleanup()
        return False

    def _extract_repo_name(self, url: str) -> str:
        """
        Extract repository name from URL.

        Handles various URL formats:
        - https://github.com/user/repo.git
        - git@github.com:user/repo.git
        - ssh://git@github.com/user/repo.git

        Args:
            url: Repository URL

        Returns:
            Repository name

        Raises:
            GitOperationError: If URL format is invalid
        """
        try:
            # Parse HTTP(S) URLs
            parsed = urlparse(url)
            if parsed.scheme in ["http", "https"]:
                path_parts = parsed.path.strip("/").split("/")
                if len(path_parts) >= 2:
                    return path_parts[-1].replace(".git", "")
                raise GitOperationError(
                    "Invalid repository URL", f"Could not extract repository name from: {url}"
                )

            # Handle SSH URLs (git@host:user/repo.git)
            if "@" in url and ":" in url:
                repo_part = url.split(":")[-1]
                return repo_part.split("/")[-1].replace(".git", "")

            # Handle ssh:// URLs
            if parsed.scheme == "ssh":
                path_parts = parsed.path.strip("/").split("/")
                if path_parts:
                    return path_parts[-1].replace(".git", "")

            # Fallback: try to extract from last part
            return url.split("/")[-1].replace(".git", "") or "repository"

        except Exception as e:
            raise GitOperationError("Failed to parse repository URL", f"URL: {url}, Error: {e}")

    def clone_or_pull(
        self, workspace_dir: Path, depth: int = 1, single_branch: bool = True
    ) -> Path:
        """
        Clone repository or pull latest changes if it exists.

        Uses shallow cloning with --depth=1 for better performance.
        Implements --filter=blob:none for even faster clones.

        Args:
            workspace_dir: Directory to clone repository into
            depth: Clone depth (1 for shallow clone)
            single_branch: Whether to clone only single branch

        Returns:
            Path to cloned repository

        Raises:
            GitOperationError: If clone or pull fails

        Example:
            >>> manager = GitRepoManager("https://github.com/user/repo.git")
            >>> repo_path = manager.clone_or_pull(Path("./workspace"))
            >>> print(repo_path)
            /path/to/workspace/repo
        """
        # Ensure workspace directory exists
        workspace_dir = Path(workspace_dir)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Set repository directory
        self.repo_dir = workspace_dir / self._repo_name

        try:
            if self.repo_dir.exists():
                # Repository exists, pull latest changes
                return self._pull_latest(self.repo_dir)
            else:
                # Clone repository
                return self._clone_repository(
                    self.repo_dir, depth=depth, single_branch=single_branch
                )

        except git.GitCommandError as e:
            raise GitOperationError(
                "Git operation failed", f"Command: {e.command}, Output: {e.stderr}"
            )
        except Exception as e:
            raise GitOperationError("Unexpected error during Git operation", str(e))

    def _clone_repository(
        self, target_dir: Path, depth: int = 1, single_branch: bool = True
    ) -> Path:
        """
        Clone repository with optimized settings.

        Args:
            target_dir: Directory to clone into
            depth: Clone depth
            single_branch: Whether to clone single branch

        Returns:
            Path to cloned repository
        """
        logger.info(f"Cloning repository: {self.repo_url} (branch: {self.branch})")

        try:
            # Clone with optimal settings
            git.Repo.clone_from(
                url=self.repo_url,
                to_path=str(target_dir),
                branch=self.branch,
                depth=depth,
                single_branch=single_branch,
                # Use blob filter for faster clones
                filter="blob:none" if depth == 1 else None,
            )

            logger.info(f"Successfully cloned repository to: {target_dir}")
            return target_dir

        except git.GitCommandError as e:
            # Cleanup partial clone on failure
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)

            raise GitOperationError(
                f"Failed to clone repository: {self.repo_url}",
                f"Branch: {self.branch}, Error: {e.stderr}",
            )

    def _pull_latest(self, repo_dir: Path) -> Path:
        """
        Pull latest changes from remote.

        Args:
            repo_dir: Repository directory

        Returns:
            Path to repository
        """
        logger.info(f"Pulling latest changes from {self.branch}")

        try:
            repo = git.Repo(repo_dir)

            # Ensure remote exists
            if not repo.remotes:
                repo.create_remote("origin", self.repo_url)

            origin = repo.remotes.origin

            # Fetch latest changes
            origin.fetch()

            # Reset to remote branch
            repo.git.reset("--hard", f"origin/{self.branch}")

            logger.info(f"Successfully updated repository: {repo_dir}")
            return repo_dir

        except git.GitCommandError as e:
            raise GitOperationError(
                f"Failed to pull latest changes: {repo_dir}",
                f"Branch: {self.branch}, Error: {e.stderr}",
            )

    def cleanup(self) -> None:
        """
        Remove cloned repository directory.

        This should be called manually when done processing,
        or use the context manager for automatic cleanup.

        Example:
            >>> manager = GitRepoManager(url)
            >>> repo_path = manager.clone_or_pull(workspace)
            >>> # ... process files
            >>> manager.cleanup()
        """
        if self.repo_dir and self.repo_dir.exists():
            try:
                shutil.rmtree(self.repo_dir, ignore_errors=True)
                logger.info(f"Cleaned up repository: {self.repo_dir}")
                self.repo_dir = None
            except Exception as e:
                logger.warning(f"Failed to cleanup repository {self.repo_dir}: {e}")

    def get_commit_info(self) -> Optional[dict]:
        """
        Get information about current commit.

        Returns:
            Dictionary with commit info, or None if repository not cloned

        Example:
            >>> info = manager.get_commit_info()
            >>> print(info['sha'])
            abc123...
        """
        if not self.repo_dir or not self.repo_dir.exists():
            return None

        try:
            repo = git.Repo(self.repo_dir)
            commit = repo.head.commit

            return {
                "sha": commit.hexsha,
                "short_sha": commit.hexsha[:7],
                "author": str(commit.author),
                "date": commit.committed_datetime,
                "message": commit.message.strip(),
                "branch": self.branch,
            }
        except Exception as e:
            logger.warning(f"Failed to get commit info: {e}")
            return None
