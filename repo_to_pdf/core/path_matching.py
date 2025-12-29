"""Utilities for matching repo-relative paths against POSIX-style glob patterns."""

from __future__ import annotations

import fnmatch
from functools import lru_cache
from pathlib import Path
from typing import Iterable, List, Sequence, Union

PathLike = Union[str, Path]


def _split_posix_parts(value: str) -> List[str]:
    normalized = (value or "").strip().replace("\\", "/")
    normalized = normalized.lstrip("./").lstrip("/")
    return [p for p in normalized.split("/") if p and p != "."]


def posix_glob_match(path: PathLike, pattern: str, *, case_sensitive: bool = False) -> bool:
    """
    Match a repo-relative path against a POSIX-style glob pattern.

    Semantics:
    - Path separator is always '/' (Windows '\\' is normalized).
    - '*' and '?' do not cross path separators.
    - '**' (as a full path segment) matches zero or more path segments.
    """
    path_str = path.as_posix() if isinstance(path, Path) else str(path)
    path_parts = _split_posix_parts(path_str)
    pattern_parts = _split_posix_parts(pattern)

    def seg_match(segment: str, pat: str) -> bool:
        if not case_sensitive:
            segment = segment.lower()
            pat = pat.lower()
        return fnmatch.fnmatchcase(segment, pat)

    @lru_cache(maxsize=None)
    def dp(i: int, j: int) -> bool:
        if j >= len(pattern_parts):
            return i >= len(path_parts)

        pat = pattern_parts[j]
        if pat == "**":
            return dp(i, j + 1) or (i < len(path_parts) and dp(i + 1, j))

        if i >= len(path_parts):
            return False

        return seg_match(path_parts[i], pat) and dp(i + 1, j + 1)

    return dp(0, 0)


def posix_glob_match_any(
    path: PathLike, patterns: Sequence[str] | None, *, case_sensitive: bool = False
) -> bool:
    """Return True if path matches any pattern in patterns."""
    if not patterns:
        return False
    return any(posix_glob_match(path, pat, case_sensitive=case_sensitive) for pat in patterns if pat)


def normalize_patterns(patterns: Iterable[str] | None) -> List[str]:
    """Normalize patterns by trimming whitespace and normalizing separators."""
    if not patterns:
        return []
    out: List[str] = []
    for pattern in patterns:
        pat = (pattern or "").strip().replace("\\", "/")
        pat = pat.lstrip("./").lstrip("/")
        if pat:
            out.append(pat)
    return out

