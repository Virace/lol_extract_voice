"""验证项目保留的最小公开 Python 导入面。"""

from __future__ import annotations

from importlib import import_module

import pytest

PUBLIC_SYMBOLS = [
    (
        "lol_audio_unpack",
        (
            "__version__",
            "setup_app",
        ),
    ),
    (
        "lol_audio_unpack.app",
        (
            "AppConfig",
            "AppContext",
            "AppContextValidationError",
            "AppPaths",
            "EntityResult",
            "LolAudioUnpackApp",
            "OperationOptions",
            "OperationProgress",
            "ResultStatus",
            "ResourcePackWadRef",
            "RunResult",
            "StageResult",
            "WavOutputOptions",
            "create_app_context",
        ),
    ),
    (
        "lol_audio_unpack.config",
        (
            "ConfigSection",
            "CommandConfigField",
            "SettingKey",
            "SharedSettingField",
            "build_settings",
            "load_command_config",
            "load_settings",
            "resolve_default_path",
            "write_command_config",
            "write_settings",
        ),
    ),
    (
        "lol_audio_unpack.cli",
        ("main",),
    ),
    (
        "lol_audio_unpack.model",
        (
            "AudioEntityData",
            "generate_champion_tasks",
            "generate_map_tasks",
        ),
    ),
    (
        "lol_audio_unpack.runtime.wav",
        (
            "TranscodeCoordinator",
            "TranscodePaths",
            "TranscodeProgress",
            "TranscodeSummary",
            "build_output_path",
            "build_transcode_paths",
            "resolve_decode_config",
            "run_tree",
            "run_worker",
        ),
    ),
    (
        "lol_audio_unpack.unpack",
        (
            "generate_output_path",
            "unpack_all",
            "unpack_champion",
            "unpack_champions",
            "unpack_entity",
            "unpack_map",
            "unpack_maps",
            "unpack_resource_pack",
            "unpack_resource_packs",
        ),
    ),
    (
        "lol_audio_unpack.mapping",
        (
            "RuntimeCache",
            "build_all",
            "build_champion",
            "build_champions",
            "build_entity",
            "build_map",
            "build_maps",
            "build_resource_pack",
            "build_resource_packs",
            "describe_hirc_backend",
            "execute_tasks",
            "integrate_entity",
        ),
    ),
    (
        "lol_audio_unpack.manager",
        (
            "BinUpdater",
            "DataReader",
            "DataUpdater",
        ),
    ),
]


@pytest.mark.parametrize(("module_name", "symbols"), PUBLIC_SYMBOLS)
def test_public_symbols_are_importable(module_name: str, symbols: tuple[str, ...]) -> None:
    """公开入口应能从其声明模块稳定导入。

    Args:
        module_name: 待验证的公开模块。
        symbols: 该模块承诺保留的关键符号。
    """
    module = import_module(module_name)

    missing = [name for name in symbols if not hasattr(module, name)]

    assert not missing, f"{module_name} 缺少公开符号: {missing}"
