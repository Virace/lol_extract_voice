"""共享的 CLI 显式命令构造与校验 helper。"""

from __future__ import annotations

from dataclasses import dataclass

from lol_audio_unpack.app_context import OperationOptions, SourceMode, WavOutputOptions
from lol_audio_unpack.config_schema import DEFAULT_REMOTE_LIVE_REGION, DEFAULT_SHARED_SETTINGS, SettingKey
from lol_audio_unpack.utils.runtime_paths import (
    RuntimePaths,
    detect_runtime_paths,
    get_default_output_root,
    get_default_wwiser_path,
    resolve_runtime_path,
)

DEFAULT_CLI_MAX_WORKERS = OperationOptions().max_workers
_DEFAULT_WAV_OPTIONS = WavOutputOptions()
DEFAULT_WAV_WORKERS = _DEFAULT_WAV_OPTIONS.worker_count
DEFAULT_WAV_TIMEOUT = _DEFAULT_WAV_OPTIONS.timeout_seconds
DEFAULT_WAV_RETRIES = _DEFAULT_WAV_OPTIONS.max_retries
DEFAULT_WAV_FORMAT = _DEFAULT_WAV_OPTIONS.format
DEFAULT_GAME_REGION = str(DEFAULT_SHARED_SETTINGS[SettingKey.GAME_REGION])
DEFAULT_SOURCE_MODE = str(DEFAULT_SHARED_SETTINGS[SettingKey.SOURCE_MODE])
DEFAULT_EXCLUDE_TYPE = str(DEFAULT_SHARED_SETTINGS[SettingKey.EXCLUDE_TYPE])
VALID_ACTIONS = ("update", "extract", "mapping")


class CliInvocationValidationError(ValueError):
    """显式命令构造前的输入校验错误。"""


@dataclass(slots=True, frozen=True)
class CliInvocationRequest:
    """构造完整 CLI 命令所需的结构化输入。"""

    actions: tuple[str, ...]
    settings: tuple[tuple[str, str | bool], ...] = ()
    champions: str | None = None
    maps: str | None = None
    max_workers: int = DEFAULT_CLI_MAX_WORKERS
    force: bool = False
    skip_events: bool = False
    integrate_data: bool | None = None
    wav_enabled: bool = False
    wav_workers: int = DEFAULT_WAV_WORKERS
    wav_timeout: int = DEFAULT_WAV_TIMEOUT
    wav_retries: int = DEFAULT_WAV_RETRIES
    wav_format: str = DEFAULT_WAV_FORMAT

    def to_settings(self) -> dict[str, str | bool]:
        """返回共享配置映射。"""
        return dict(self.settings)


def quote_cli_arg(arg: str) -> str:
    """以 shell 无关的方式格式化单个命令行参数。"""
    if not arg:
        return "''"

    safe_chars = "-_./,:=\\"
    if all(char.isalnum() or char in safe_chars for char in arg):
        return arg
    return "'" + arg.replace("'", "''") + "'"


def render_cli_command(argv: list[str]) -> str:
    """将 argv 渲染为可复制的 CLI 命令文本。"""
    return " ".join(quote_cli_arg(arg) for arg in argv)


def _clean_setting_value(key: str, value: str | bool | None) -> str | bool | None:
    """标准化共享配置值。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip()
    if not text:
        return "" if key == SettingKey.EXCLUDE_TYPE else None
    return text


def _normalized_settings(request: CliInvocationRequest) -> dict[str, str | bool]:
    """返回去掉空白后的共享配置。"""
    settings: dict[str, str | bool] = {}
    for key, raw_value in request.settings:
        value = _clean_setting_value(key, raw_value)
        if value is None:
            continue
        settings[key] = value
    return settings


def _append_optional_arg(argv: list[str], flag: str, value: str | None) -> None:
    """仅当值非空时追加一个二元参数。"""
    if value is None:
        return
    argv.extend([flag, value])


def _normalize_actions(actions: tuple[str, ...]) -> tuple[str, ...]:
    """去重并保持动作顺序。"""
    return tuple(dict.fromkeys(actions))


def validate_cli_invocation_request(
    request: CliInvocationRequest,
    *,
    runtime_paths: RuntimePaths | None = None,
    check_required_settings: bool = True,
) -> None:
    """校验显式命令请求是否可安全构造。"""
    _ = runtime_paths
    actions = _normalize_actions(request.actions)
    if not actions:
        raise CliInvocationValidationError("至少需要提供一个动作：update / extract / mapping。")

    invalid_actions = [action for action in actions if action not in VALID_ACTIONS]
    if invalid_actions:
        raise CliInvocationValidationError(f"存在不支持的动作: {', '.join(invalid_actions)}")

    if request.wav_enabled and "extract" not in actions:
        raise CliInvocationValidationError("--wav 只能与 extract 动作一起使用。")

    wav_tuning_explicit = (
        request.wav_workers != DEFAULT_WAV_WORKERS
        or request.wav_timeout != DEFAULT_WAV_TIMEOUT
        or request.wav_retries != DEFAULT_WAV_RETRIES
        or request.wav_format != DEFAULT_WAV_FORMAT
    )
    if wav_tuning_explicit and not request.wav_enabled:
        raise CliInvocationValidationError(
            "--wav-workers / --wav-timeout / --wav-retries / --wav-format 只能与 --wav 一起使用。"
        )

    if request.integrate_data is not None and "mapping" not in actions:
        raise CliInvocationValidationError("--integrate-data 只能与 mapping 动作一起使用。")

    settings = _normalized_settings(request)
    source_mode = str(settings.get(SettingKey.SOURCE_MODE, DEFAULT_SOURCE_MODE) or DEFAULT_SOURCE_MODE).strip().lower()
    if source_mode not in {mode.value for mode in SourceMode}:
        raise CliInvocationValidationError(f"source_mode 无效: {source_mode}")

    if check_required_settings and source_mode == SourceMode.LOCAL_PATH.value and not settings.get(SettingKey.GAME_PATH):
        raise CliInvocationValidationError("当前命令缺少本地模式必需的共享配置: game_path")

    remote_keys = (
        SettingKey.REMOTE_VERSION,
        SettingKey.REMOTE_LCU_MANIFEST_URL,
        SettingKey.REMOTE_GAME_MANIFEST_URL,
    )
    provided_remote_keys = [key for key in remote_keys if settings.get(key)]
    if provided_remote_keys and len(provided_remote_keys) != len(remote_keys):
        raise CliInvocationValidationError(
            "若显式指定远端快照，则 remote_version、remote_lcu_manifest_url、remote_game_manifest_url 必须同时提供。"
        )


def build_explicit_cli_argv(
    request: CliInvocationRequest,
    *,
    runtime_paths: RuntimePaths | None = None,
) -> list[str]:
    """将结构化请求转换为完整显式 CLI argv。"""
    runtime = runtime_paths or detect_runtime_paths()
    validate_cli_invocation_request(request, runtime_paths=runtime)

    settings = _normalized_settings(request)
    actions = _normalize_actions(request.actions)
    argv = ["uv", "run", "unpack", *actions]

    source_mode = str(settings.get(SettingKey.SOURCE_MODE, DEFAULT_SOURCE_MODE) or DEFAULT_SOURCE_MODE).strip().lower()
    game_path = settings.get(SettingKey.GAME_PATH)
    output_path = settings.get(SettingKey.OUTPUT_PATH)
    game_region = settings.get(SettingKey.GAME_REGION)
    exclude_type = settings.get(SettingKey.EXCLUDE_TYPE)
    wwiser_path = settings.get(SettingKey.WWISER_PATH)
    with_bp_vo = bool(settings.get(SettingKey.WITH_BP_VO, False))
    group_by_type = bool(settings.get(SettingKey.GROUP_BY_TYPE, False))
    remote_live_region = str(settings.get(SettingKey.REMOTE_LIVE_REGION, DEFAULT_REMOTE_LIVE_REGION) or DEFAULT_REMOTE_LIVE_REGION)
    cleanup_remote = bool(settings.get(SettingKey.CLEANUP_REMOTE, True))

    if source_mode != DEFAULT_SOURCE_MODE:
        argv.extend(["--source-mode", source_mode])
    if isinstance(game_path, str):
        argv.extend(["--game-path", game_path])

    if isinstance(output_path, str):
        resolved_output_path = resolve_runtime_path(output_path, runtime_paths=runtime)
        if resolved_output_path != get_default_output_root(runtime):
            argv.extend(["--output-path", output_path])

    if isinstance(game_region, str) and game_region != DEFAULT_GAME_REGION:
        argv.extend(["--game-region", game_region])
    if exclude_type is not None and str(exclude_type) != DEFAULT_EXCLUDE_TYPE:
        argv.extend(["--exclude-type", str(exclude_type)])
    if with_bp_vo:
        argv.append("--with-bp-vo")
    if group_by_type:
        argv.append("--group-by-type")

    if source_mode == SourceMode.REMOTE_SNAPSHOT.value:
        if remote_live_region != DEFAULT_REMOTE_LIVE_REGION:
            argv.extend(["--remote-live-region", remote_live_region])
        if not cleanup_remote:
            argv.append("--no-cleanup-remote")
        _append_optional_arg(argv, "--remote-version", settings.get(SettingKey.REMOTE_VERSION) if isinstance(settings.get(SettingKey.REMOTE_VERSION), str) else None)
        _append_optional_arg(
            argv,
            "--remote-lcu-manifest-url",
            settings.get(SettingKey.REMOTE_LCU_MANIFEST_URL) if isinstance(settings.get(SettingKey.REMOTE_LCU_MANIFEST_URL), str) else None,
        )
        _append_optional_arg(
            argv,
            "--remote-game-manifest-url",
            settings.get(SettingKey.REMOTE_GAME_MANIFEST_URL) if isinstance(settings.get(SettingKey.REMOTE_GAME_MANIFEST_URL), str) else None,
        )

    if "mapping" in actions and isinstance(wwiser_path, str):
        resolved_wwiser_path = resolve_runtime_path(wwiser_path, runtime_paths=runtime)
        if resolved_wwiser_path != get_default_wwiser_path(runtime):
            argv.extend(["--wwiser-path", wwiser_path])

    _append_optional_arg(argv, "--champions", request.champions)
    _append_optional_arg(argv, "--maps", request.maps)

    if request.max_workers != DEFAULT_CLI_MAX_WORKERS:
        argv.extend(["--max-workers", str(request.max_workers)])
    if request.force:
        argv.append("--force")
    if request.skip_events:
        argv.append("--skip-events")

    if "mapping" in actions and request.integrate_data is False:
        argv.append("--no-integrate-data")

    if request.wav_enabled:
        argv.append("--wav")
        if request.wav_workers != DEFAULT_WAV_WORKERS:
            argv.extend(["--wav-workers", str(request.wav_workers)])
        if request.wav_timeout != DEFAULT_WAV_TIMEOUT:
            argv.extend(["--wav-timeout", str(request.wav_timeout)])
        if request.wav_retries != DEFAULT_WAV_RETRIES:
            argv.extend(["--wav-retries", str(request.wav_retries)])
        if request.wav_format != DEFAULT_WAV_FORMAT:
            argv.extend(["--wav-format", request.wav_format])

    return argv


def build_explicit_cli_command(
    request: CliInvocationRequest,
    *,
    runtime_paths: RuntimePaths | None = None,
) -> str:
    """构造完整显式的 CLI 命令文本。"""
    return render_cli_command(build_explicit_cli_argv(request, runtime_paths=runtime_paths))


__all__ = [
    "CliInvocationRequest",
    "CliInvocationValidationError",
    "DEFAULT_CLI_MAX_WORKERS",
    "DEFAULT_WAV_FORMAT",
    "DEFAULT_WAV_RETRIES",
    "DEFAULT_WAV_TIMEOUT",
    "DEFAULT_WAV_WORKERS",
    "build_explicit_cli_argv",
    "build_explicit_cli_command",
    "quote_cli_arg",
    "render_cli_command",
    "validate_cli_invocation_request",
]
