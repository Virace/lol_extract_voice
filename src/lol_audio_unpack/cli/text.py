"""CLI 文本目录。"""

DEFAULT_LOCALE = "zh_CN"

_TEXTS: dict[str, dict[str, str]] = {
    "zh_CN": {
        "parser.unpack.description": "一个极简、高效的英雄联盟音频提取工具 (v3)",
        "parser.mapping.description": "构建事件映射",
        "action.update": "更新数据",
        "action.extract": "解包音频",
        "action.wav": "转码 WAV",
        "action.mapping": "构建映射",
        "help.log_level": "设置日志输出等级，默认为 INFO。",
        "help.dev": "启用开发者模式，默认配置文件名切换为 dev 版本并保留临时文件。",
        "help.max_workers": "批量运行时使用的最大线程数。默认为 4。",
        "help.force": "强制更新数据，忽略版本检查。",
        "help.skip_events": "跳过事件数据处理，仅对 update 流程生效。",
        "help.with_bp_vo": "是否附带大厅选用/禁用语音资源。",
        "help.enable_league_tools_log": "启用 league_tools 模块日志。",
        "help.config_file": "启用绝对独占的配置文件模式；动作与参数都从配置文件读取。仅写 -c 时读取默认 INI，写 -c PATH 时读取指定 INI。",
        "group.target.title": "实体选择",
        "group.target.description": "多个动作共享的目标范围选择",
        "help.shared.champions": "指定英雄范围；无参数时表示所有英雄。",
        "help.shared.maps": "指定地图范围；无参数时表示所有地图。",
        "group.config.title": "共享配置",
        "group.config.description": "纯 CLI 模式下显式提供的共享配置",
        "help.source_mode": "显式指定内容来源模式。",
        "help.game_path": "显式指定游戏客户端根目录。",
        "help.output_path": "显式指定输出目录。",
        "help.game_region": "显式指定语言区域。",
        "help.exclude_type": "显式指定排除的音频类型。",
        "help.wwiser_path": "显式指定 wwiser 路径。",
        "help.group_by_type": "显式指定是否按音频类型分组输出。",
        "help.remote_live_region": "显式指定远端快照 live region。",
        "help.cleanup_remote": "显式指定 remote_snapshot 模式下是否在成功后清理产物。",
        "help.remote_version": "显式指定远端快照版本。",
        "help.remote_lcu_manifest_url": "显式指定远端 LCU manifest URL。",
        "help.remote_game_manifest_url": "显式指定远端 GAME manifest URL。",
        "help.update.champions": "更新英雄数据；无参数时更新所有英雄。",
        "help.update.maps": "更新地图数据；无参数时更新所有地图。",
        "help.extract.champions": "解包英雄音频；无参数时解包所有英雄。",
        "help.extract.maps": "解包地图音频；无参数时解包所有地图。",
        "help.mapping.champions": "构建英雄事件映射；无参数时构建所有英雄。",
        "help.mapping.maps": "构建地图事件映射；无参数时构建所有地图。",
        "help.mapping.integrate_data": "生成整合数据文件（包含完整实体信息、banks 和 mapping 数据）。",
        "help.version": "显示当前脚本的版本号。",
        "help.actions": "要执行的动作列表，支持顺序提供多个动作，如 `update extract wav`。",
        "help.mapping.integrate_data_global": "mapping 阶段是否生成整合数据文件；未显式指定时默认开启。",
        "help.wav_workers": "设置 wav 动作使用的转码并发进程数。",
        "help.wav_timeout": "设置单个 WAV 转码任务的超时时间（秒）。",
        "help.wav_retries": "设置单个 WAV 转码任务的最大重试次数。",
        "help.wav_format": "设置 WAV 输出格式。",
        "stage.update": "数据更新",
        "stage.extract": "音频解包",
        "stage.wav": "WAV 转码",
        "stage.mapping": "事件映射",
        "error.actions.required": "错误：必须提供至少一个动作：update / extract / wav / mapping。",
        "error.action.invalid": "错误：存在不支持的动作。",
    }
}


def text(key: str, locale: str | None = None) -> str:
    """读取 CLI 文本目录中的文案。

    Args:
        key: 文案键。
        locale: 语言区域；为空时使用默认值 ``zh_CN``。

    Returns:
        对应 key 的文案字符串。

    Raises:
        KeyError: 当 locale 不存在或 key 缺失时抛出。
    """
    resolved_locale = DEFAULT_LOCALE if locale is None else locale
    locale_text = _TEXTS.get(resolved_locale)
    if locale_text is None:
        raise KeyError(f"cli text key '{key}' is not defined for locale '{resolved_locale}'")

    value = locale_text.get(key)
    if value is None:
        raise KeyError(f"cli text key '{key}' is not defined for locale '{resolved_locale}'")
    return value
