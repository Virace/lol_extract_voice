"""测试事件映射构建阶段的日志汇总行为。"""

from pathlib import Path
from types import SimpleNamespace

from loguru import logger

import lol_audio_unpack.mapping as mapping_module
from lol_audio_unpack.mapping import build_audio_event_mapping
from lol_audio_unpack.model import AudioEntityData


class _FakeReader:
    """提供 `build_audio_event_mapping` 所需最小读取接口。"""

    version = "test-version"

    @staticmethod
    def get_languages() -> list[str]:
        """返回测试使用的语言列表。"""
        return ["zh_CN"]


class _FakeWad:
    """将请求提取的 bnk 文件写入缓存目录。"""

    @staticmethod
    def extract(bnk_paths: list[str], out_dir: Path) -> None:
        """模拟 WAD 提取行为。"""
        for bnk_rel_path in bnk_paths:
            target = Path(out_dir) / bnk_rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fake-bnk")


class _FakeAudioMapping:
    """提供测试所需的最小映射对象。"""

    def __init__(self, forward_mapping: dict[str, list[int]]) -> None:
        self.forward_mapping = forward_mapping

    def merge_with(self, other: "_FakeAudioMapping") -> None:
        """合并其他映射结果。"""
        for event_name, sound_ids in other.forward_mapping.items():
            merged_ids = self.forward_mapping.setdefault(event_name, [])
            merged_ids.extend(sound_ids)
            self.forward_mapping[event_name] = sorted(set(merged_ids))


class _FakeAudioEventMapper:
    """根据测试事件列表返回固定映射结果。"""

    def __init__(self, event_list: list[str], _hirc: object) -> None:
        self._event_list = tuple(event_list)

    def build_mapping(self) -> _FakeAudioMapping:
        """返回固定映射结果，模拟部分事件未映射。"""
        if self._event_list == ("evt_ok", "evt_skip"):
            return _FakeAudioMapping({"evt_ok": [101]})
        return _FakeAudioMapping({})


def _build_fake_ctx() -> SimpleNamespace:
    """创建最小运行上下文。"""
    return SimpleNamespace(config=SimpleNamespace(dev_mode=False, wwiser_path=None))


def test_build_audio_event_mapping_uses_single_success_summary(monkeypatch, tmp_path: Path) -> None:
    """类别级完成日志应降为 debug，实体级只保留一条统计 success。"""
    cache_dir = tmp_path / "cache"
    hash_dir = tmp_path / "hashes"
    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "root.wad.client").write_bytes(b"fake-wad")

    monkeypatch.setattr(mapping_module, "_get_cache_base_path", lambda _ctx: cache_dir)
    monkeypatch.setattr(mapping_module, "_get_hash_base_path", lambda _ctx: hash_dir)
    monkeypatch.setattr(mapping_module, "_get_game_base_path", lambda _ctx: game_dir)
    monkeypatch.setattr(mapping_module, "_get_wad_instance", lambda _wad_path, runtime_cache=None: _FakeWad())
    monkeypatch.setattr(mapping_module, "AudioEventMapper", _FakeAudioEventMapper)
    monkeypatch.setattr(mapping_module, "write_data", lambda *args, **kwargs: None)

    def fake_get_cached_hirc(*, bnk_path: Path, **_kwargs) -> object:
        if bnk_path.name == "bad_events.bnk":
            raise RuntimeError("读取 MusicSwitch.rule_destination_count 失败")
        return object()

    monkeypatch.setattr(mapping_module, "_get_cached_hirc", fake_get_cached_hirc)

    entity_data = AudioEntityData(
        entity_id="1",
        entity_name="Test Entity",
        entity_alias="test-entity",
        entity_title="测试实体",
        entity_type="champion",
        sub_entities={
            "1001": {
                "name": "Test Skin",
                "categories": {
                    "CAT_OK": [["ok_events.bnk"]],
                    "CAT_ERR": [["bad_events.bnk"]],
                },
            }
        },
        wad_root="root.wad.client",
        wad_language=None,
        events={
            "1001": {
                "events": {
                    "CAT_OK": ["evt_ok", "evt_skip"],
                    "CAT_ERR": ["evt_problem"],
                }
            }
        },
    )

    log_lines: list[str] = []
    logger.enable("lol_audio_unpack")
    sink_id = logger.add(
        lambda message: log_lines.append(str(message).rstrip()),
        format="{level}|{message}",
    )

    try:
        build_audio_event_mapping(
            entity_data=entity_data,
            reader=_FakeReader(),
            wwiser_manager=None,
            integrate_data=False,
            runtime_cache=None,
            ctx=_build_fake_ctx(),
        )
    finally:
        logger.remove(sink_id)

    assert any("DEBUG|完成 CAT_OK 的映射" in line for line in log_lines)
    assert not any("SUCCESS|完成 CAT_OK 的映射" in line for line in log_lines)
    assert any("WARNING|处理路径组合 1 时出错: 读取 MusicSwitch.rule_destination_count 失败" in line for line in log_lines)

    warning_lines = [line for line in log_lines if "WARNING|" in line]
    assert any("Test Entity 的事件映射统计" in line for line in warning_lines)
    assert any("成功映射事件 1 个" in line for line in warning_lines)
    assert any("异常事件 1 个" in line for line in warning_lines)
    assert any("未映射跳过 1 个" in line for line in warning_lines)
    assert not any("SUCCESS|Test Entity 的事件映射统计" in line for line in log_lines)
