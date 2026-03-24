"""验证基于 Git 描述信息生成运行时版本号的规则。"""

from __future__ import annotations

from pathlib import Path

import pytest

from lol_audio_unpack.utils import versioning


def test_extract_windows_file_version_reads_utf16_version_string() -> None:
    payload = (
        b"prefix"
        + "ProductVersion".encode("utf-16le")
        + b"\x00\x00"
        + "16.5.751.1533".encode("utf-16le")
        + b"suffix"
    )

    assert versioning.extract_windows_file_version(payload) == "16.5.751.1533"


def test_derive_version_from_git_describe_returns_release_for_exact_tag() -> None:
    assert versioning.derive_version_from_git_describe("3.5.0-0-g6d3be2c", fallback_version="3.5.1.dev0") == "3.5.0"


def test_derive_version_from_git_describe_uses_next_patch_dev_for_ahead_commits() -> None:
    assert (
        versioning.derive_version_from_git_describe("3.5.0-63-g6d3be2c", fallback_version="3.5.1.dev0")
        == "3.5.1.dev63+g6d3be2c"
    )


def test_derive_version_from_git_describe_marks_dirty_worktree() -> None:
    assert (
        versioning.derive_version_from_git_describe("3.5.0-63-g6d3be2c-dirty", fallback_version="3.5.1.dev0")
        == "3.5.1.dev63+g6d3be2c.dirty"
    )


def test_derive_version_from_git_describe_accepts_v_prefix_tag() -> None:
    assert (
        versioning.derive_version_from_git_describe("v3.4.0-2-gabc1234", fallback_version="3.5.1.dev0")
        == "3.4.1.dev2+gabc1234"
    )


def test_resolve_runtime_version_falls_back_when_git_describe_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _raise_git_error(repo_root: Path) -> str:
        raise RuntimeError(f"boom: {repo_root}")

    monkeypatch.setattr(versioning, "describe_git_version", _raise_git_error)

    assert versioning.resolve_runtime_version(tmp_path, "3.5.1.dev0") == "3.5.1.dev0"
