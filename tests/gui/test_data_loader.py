"""测试 GUI 数据加载器"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lol_audio_unpack.gui.service.data_loader import (
    EntityDataLoader,
    check_entity_status,
    resolve_entity_audio_paths,
)


@pytest.fixture
def mock_app_context():
    """创建 mock AppContext"""
    ctx = Mock()
    ctx.paths.audio_path = "/tmp/audios"
    ctx.paths.hash_path = Path("/tmp/hashes")
    ctx.paths.output_path = "/tmp/output"
    ctx.config.group_by_type = False
    ctx.config.include_types = ["VO", "SFX", "MUSIC"]
    return ctx


@pytest.fixture
def mock_entity_data():
    """创建 mock AudioEntityData"""
    entity = Mock()
    entity.entity_id = "1"
    entity.entity_alias = "annie"
    entity.entity_name = "安妮"
    entity.entity_title = "黑暗之女"
    entity.entity_type = "champion"
    return entity


def test_resolve_entity_audio_paths_no_group(mock_app_context, mock_entity_data):
    """测试不分组时的路径解析"""
    with patch("pathlib.Path.exists", return_value=True):
        paths = resolve_entity_audio_paths(mock_app_context, mock_entity_data, "14.1.0")
        assert len(paths) == 1
        assert "champions" in str(paths[0])
        assert "1·annie·安妮·黑暗之女" in str(paths[0])


def test_resolve_entity_audio_paths_with_group(mock_app_context, mock_entity_data):
    """测试分组时的路径解析"""
    mock_app_context.config.group_by_type = True
    expected_types_count = len(mock_app_context.config.include_types)
    with patch("pathlib.Path.exists", return_value=True):
        paths = resolve_entity_audio_paths(mock_app_context, mock_entity_data, "14.1.0")
        assert len(paths) == expected_types_count


def test_check_entity_status_both_exist(mock_app_context, mock_entity_data):
    """测试音频和映射都存在的情况"""
    with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.iterdir", return_value=[Mock()]):
        audio_status, mapping_status = check_entity_status(mock_app_context, mock_entity_data, "14.1.0")
        assert audio_status == "已存在"
        assert mapping_status == "已存在"


def test_check_entity_status_none_exist(mock_app_context, mock_entity_data):
    """测试音频和映射都不存在的情况"""
    with patch("pathlib.Path.exists", return_value=False):
        audio_status, mapping_status = check_entity_status(mock_app_context, mock_entity_data, "14.1.0")
        assert audio_status == "未存在"
        assert mapping_status == "未存在"


def test_entity_data_loader_load_entities(mock_app_context):
    """测试实体数据加载"""
    with patch("lol_audio_unpack.gui.service.data_loader.DataReader") as mock_reader_cls:
        mock_reader = Mock()
        mock_reader.version = "14.1.0"
        mock_reader.get_champions.return_value = [{"id": 1}]
        mock_reader_cls.return_value = mock_reader

        with patch("lol_audio_unpack.gui.service.data_loader.AudioEntityData.from_champion") as mock_from_champion:
            mock_entity = Mock()
            mock_entity.entity_id = "1"
            mock_entity.entity_name = "安妮"
            mock_entity.entity_title = "黑暗之女"
            mock_entity.entity_alias = "annie"
            mock_from_champion.return_value = mock_entity

            with patch("lol_audio_unpack.gui.service.data_loader.check_entity_status", return_value=("已存在", "未存在")):
                loader = EntityDataLoader(mock_app_context)
                data = loader.load_entities("champions")

                assert len(data) == 1
                assert data[0]["id"] == "1"
                assert data[0]["name"] == "安妮·黑暗之女"
                assert data[0]["alias"] == "annie"
                assert data[0]["audio"] == "已存在"
                assert data[0]["mapping"] == "未存在"
