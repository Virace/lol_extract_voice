"""运行时路径语义测试。"""

from pathlib import Path

from lol_audio_unpack.utils.runtime_paths import detect_runtime_paths, get_default_output_root


def test_detect_runtime_paths_uses_cwd_for_source_runs(tmp_path: Path) -> None:
    """源码运行时应以当前工作目录作为默认根目录。"""
    source_cwd = tmp_path / "workspace"
    source_cwd.mkdir(parents=True, exist_ok=True)
    executable = tmp_path / "python" / "python.exe"

    runtime_paths = detect_runtime_paths(
        is_frozen=False,
        cwd=source_cwd,
        executable=executable,
    )

    assert runtime_paths.is_frozen is False
    assert runtime_paths.launch_root == source_cwd.resolve()
    assert runtime_paths.config_root == source_cwd.resolve()
    assert runtime_paths.bundle_root == source_cwd.resolve()
    assert runtime_paths.executable_path == executable.resolve(strict=False)


def test_detect_runtime_paths_uses_executable_dir_for_frozen_runs(tmp_path: Path) -> None:
    """冻结运行时应以可执行文件所在目录作为默认根目录。"""
    source_cwd = tmp_path / "shortcut-workdir"
    source_cwd.mkdir(parents=True, exist_ok=True)
    executable = tmp_path / "bundle" / "LolAudioUnpack.exe"

    runtime_paths = detect_runtime_paths(
        is_frozen=True,
        cwd=source_cwd,
        executable=executable,
    )

    expected_root = executable.parent.resolve(strict=False)

    assert runtime_paths.is_frozen is True
    assert runtime_paths.launch_root == expected_root
    assert runtime_paths.config_root == expected_root
    assert runtime_paths.bundle_root == expected_root
    assert runtime_paths.executable_path == executable.resolve(strict=False)


def test_default_output_root_follows_launch_root(tmp_path: Path) -> None:
    """未显式指定输出目录时应基于默认启动根目录派生 ``output``。"""
    executable = tmp_path / "bundle" / "LolAudioUnpack.exe"
    runtime_paths = detect_runtime_paths(
        is_frozen=True,
        cwd=tmp_path / "elsewhere",
        executable=executable,
    )

    assert get_default_output_root(runtime_paths) == executable.parent.resolve(strict=False) / "output"
