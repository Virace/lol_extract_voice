"""BIN 来源选择与基础数据构建辅助。

该模块负责按优先级从 WAD 或本地 BIN 输入目录提取 BIN 二进制数据，
并统一加载地图 BIN、生成带标准元数据的基础数据结构。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from league_tools.formats import BIN, WAD
from loguru import logger

from lol_audio_unpack.manager.utils import build_metadata_payload

if TYPE_CHECKING:
    from lol_audio_unpack.app.types import AppContext


class BinSource:
    """承载 BIN 提取/加载与基础数据构建职责。

    将 BIN 来源（WAD 优先、本地 BIN 回退）的解析逻辑集中在此，
    供英雄/地图处理器复用。
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        ctx: AppContext,
        game_path: Path,
        version: str,
        local_bin_input_dir: Path,
        use_local_bin_flag_file: Path,
        languages: list[str] | None = None,
    ):
        """初始化 BIN 来源。

        :param ctx: 运行时上下文。
        :param game_path: 游戏客户端根目录。
        :param version: 当前游戏版本。
        :param local_bin_input_dir: 本地 BIN 输入目录。
        :param use_local_bin_flag_file: 本地 BIN 模式标志文件路径。
        :param languages: 元数据语言列表，在 update() 中初始化。
        """
        self.ctx = ctx
        self.game_path = game_path
        self.version = version
        self.local_bin_input_dir = local_bin_input_dir
        self.use_local_bin_flag_file = use_local_bin_flag_file
        self.languages: list[str] = languages if languages is not None else []

    def _is_dev_mode(self) -> bool:
        """返回当前运行是否为开发模式。"""
        return bool(self.ctx.config.dev_mode)

    def _is_local_bin_mode_enabled(self) -> bool:
        """
        检查是否启用了本地 BIN 输入模式。

        :returns: 启用返回 True，否则返回 False。
        """
        return self.use_local_bin_flag_file.exists()

    def _build_local_bin_path(self, bin_path: str) -> Path:
        """
        将 binPath 转换为本地 BIN 文件绝对路径，并阻止路径逃逸。

        :param bin_path: 数据文件中的相对 BIN 路径。
        :returns: 本地 BIN 文件绝对路径。
        :raises ValueError: 当路径越界时抛出。
        """
        local_root = self.local_bin_input_dir.resolve()
        candidate = (self.local_bin_input_dir / Path(bin_path)).resolve()
        try:
            candidate.relative_to(local_root)
        except ValueError as e:
            raise ValueError(f"检测到越界 binPath，拒绝读取: {bin_path}") from e
        return candidate

    def _extract_bin_raws(
        self,
        wad_path: Path | None,
        bin_paths: list[str],
        entity_label: str,
        local_required_dir: Path | None = None,
    ) -> list[bytes | None]:
        """
        按优先级提取 BIN 二进制数据。

        优先级:
        1) WAD 文件存在时，强制走 WAD 提取。
        2) WAD 不存在时，若存在 `.use_local_bin` 标志，则走本地目录读取。
        3) 其余情况返回空结果。

        :param wad_path: 待提取的 WAD 路径；为空表示无可用 WAD 信息。
        :param bin_paths: 目标 BIN 路径列表。
        :param entity_label: 实体标签（用于日志）。
        :param local_required_dir: 本地模式下要求存在的目录（相对于 `bin_input`）。
        :returns: 与 `bin_paths` 顺序一致的二进制数组，缺失项为 ``None``。
        :raises FileNotFoundError: 本地模式开启但目录缺失时抛出。
        :raises ValueError: 当路径越界时抛出。
        """
        if not bin_paths:
            return []

        if wad_path and wad_path.exists():
            logger.trace(f"{entity_label} 使用 WAD 读取 BIN: {wad_path}")
            return WAD(wad_path).extract(bin_paths, raw=True)

        if not self._is_local_bin_mode_enabled():
            if wad_path:
                logger.warning(f"{entity_label} 的WAD文件不存在，且未启用本地BIN模式: {wad_path}")
            else:
                logger.warning(f"{entity_label} 缺少WAD路径信息，且未启用本地BIN模式")
            return []

        if wad_path:
            logger.debug(f"{entity_label} 的WAD文件不可用，回退到本地BIN模式: {wad_path}")
        else:
            logger.debug(f"{entity_label} 缺少WAD路径信息，回退到本地BIN模式")

        if not self.local_bin_input_dir.exists():
            raise FileNotFoundError(f"{entity_label} 启用了本地BIN模式，但目录不存在: {self.local_bin_input_dir}")

        if local_required_dir is not None:
            required_path = self.local_bin_input_dir / local_required_dir
            if not required_path.exists():
                raise FileNotFoundError(f"{entity_label} 本地BIN实体目录不存在: {required_path}")

        bin_raws: list[bytes | None] = []
        missing_count = 0
        for bin_path in bin_paths:
            local_bin_file = self._build_local_bin_path(bin_path)
            if not local_bin_file.is_file():
                bin_raws.append(None)
                missing_count += 1
                continue

            file_data = local_bin_file.read_bytes()
            if not file_data:
                bin_raws.append(None)
                missing_count += 1
                continue
            bin_raws.append(file_data)

        if missing_count > 0:
            logger.debug(f"{entity_label} 本地BIN存在缺失或空文件，已按缺失处理: {missing_count}/{len(bin_paths)}")

        logger.trace(f"{entity_label} 使用本地BIN目录读取: {self.local_bin_input_dir}")
        return bin_raws

    def _load_map_bin_file(self, map_id: str, map_data: dict) -> BIN | None:
        """
        统一加载地图 BIN 文件，兼容 WAD 与本地 BIN 模式。

        :param map_id: 地图ID。
        :param map_data: 地图数据字典。
        :returns: BIN 对象；失败时返回 None。
        """
        bin_path = map_data.get("binPath")
        if not bin_path:
            return None

        wad_root = map_data.get("wad", {}).get("root")
        wad_path = self.game_path / wad_root if wad_root else None
        local_required_dir = Path(bin_path).parent

        try:
            bin_raws = self._extract_bin_raws(
                wad_path=wad_path,
                bin_paths=[bin_path],
                entity_label=f"地图 {map_id}",
                local_required_dir=local_required_dir,
            )
            if not bin_raws:
                return None
            bin_raw = bin_raws[0]
            if not bin_raw:
                return None
            return BIN(bin_raw)
        except (FileNotFoundError, ValueError):
            logger.opt(exception=True).error(f"提取或解析地图 {map_id} 的本地BIN文件时出错")
        except Exception:
            logger.opt(exception=True).error(f"提取或解析地图 {map_id} 的BIN文件时出错")
            if self._is_dev_mode():
                raise
        return None

    def _create_base_data(self, entity_id: str, entity_type: str, **extra_fields) -> dict:
        """
        创建包含元数据和实体特定信息的基础数据结构。

        :param entity_id: 实体ID（英雄ID或地图ID）
        :param entity_type: 实体类型（'champion' 或 'map'）
        :param extra_fields: 任何要添加到顶层的额外字段
        :return: 包含元数据和附加字段的基础字典
        """
        # 使用通用函数创建包含所有标准元数据的对象
        base_data = build_metadata_payload(self.version, self.languages)

        # 检查是否为事件文件（通过是否存在'skins'或'map'顶级键来判断）
        is_event_file = "skins" in extra_fields or "map" in extra_fields

        # 如果是事件文件，则从中移除 'languages' 字段
        if is_event_file and "metadata" in base_data and "languages" in base_data["metadata"]:
            del base_data["metadata"]["languages"]

        # 添加实体特定ID
        if entity_type == "champion":
            base_data["championId"] = entity_id
        elif entity_type == "map":
            base_data["mapId"] = entity_id

        # 合并任何其他的附加字段
        base_data.update(extra_fields)
        return base_data
