from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_version_suffix.py"
SPEC = importlib.util.spec_from_file_location("check_version_suffix", MODULE_PATH)
assert SPEC and SPEC.loader is not None
check_version_suffix = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_version_suffix)


def _write_version_files(repo_root: Path, version: str) -> None:
    (repo_root / "src" / "lol_audio_unpack").mkdir(parents=True, exist_ok=True)

    (repo_root / "pyproject.toml").write_text(
        f'[project]\nname = "lol-audio-unpack"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (repo_root / "src" / "lol_audio_unpack" / "__init__.py").write_text(
        f'__version__ = "{version}"\n',
        encoding="utf-8",
    )
    (repo_root / "uv.lock").write_text(
        "\n".join(
            [
                "[[package]]",
                'name = "lol-audio-unpack"',
                f'version = "{version}"',
                'source = { editable = "." }',
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_normalize_version_suffix_switches_branch_suffix() -> None:
    assert check_version_suffix.normalize_version_suffix("3.5.1.dev0+hash", "test") == "3.5.1.dev0+test"
    assert check_version_suffix.normalize_version_suffix("3.5.1.dev0", "lite") == "3.5.1.dev0+lite"
    assert check_version_suffix.normalize_version_suffix("3.5.1.dev0+test", "") == "3.5.1.dev0"


def test_sync_version_files_updates_pyproject_init_and_uv_lock(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_version_files(repo_root, "3.5.1.dev0+hash")

    changed = check_version_suffix.sync_version_files(
        repo_root=repo_root,
        pyproject_path=repo_root / "pyproject.toml",
        init_file=Path("src/lol_audio_unpack/__init__.py"),
        uv_lock_file=Path("uv.lock"),
        target_version="3.5.1.dev0+test",
    )

    assert {path.relative_to(repo_root).as_posix() for path in changed} == {
        "pyproject.toml",
        "src/lol_audio_unpack/__init__.py",
        "uv.lock",
    }
    assert 'version = "3.5.1.dev0+test"' in (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "3.5.1.dev0+test"' in (
        repo_root / "src" / "lol_audio_unpack" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert 'version = "3.5.1.dev0+test"' in (repo_root / "uv.lock").read_text(encoding="utf-8")


def test_sync_version_files_can_remove_branch_suffix_for_release_branch(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_version_files(repo_root, "3.5.1.dev0+test")

    target_version = check_version_suffix.normalize_version_suffix("3.5.1.dev0+test", "")
    changed = check_version_suffix.sync_version_files(
        repo_root=repo_root,
        pyproject_path=repo_root / "pyproject.toml",
        init_file=Path("src/lol_audio_unpack/__init__.py"),
        uv_lock_file=Path("uv.lock"),
        target_version=target_version,
    )

    assert target_version == "3.5.1.dev0"
    assert len(changed) == 3
    assert 'version = "3.5.1.dev0"' in (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "3.5.1.dev0"' in (
        repo_root / "src" / "lol_audio_unpack" / "__init__.py"
    ).read_text(encoding="utf-8")
    assert 'version = "3.5.1.dev0"' in (repo_root / "uv.lock").read_text(encoding="utf-8")
