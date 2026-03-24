"""测试 GUI 数据加载器"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lol_audio_unpack.gui.service.data_loader import (
    EntityDataLoader,
    check_entity_status,
    resolve_entity_audio_paths,
    resolve_mapping_file_path,
)


@pytest.fixture
def mock_app_context(tmp_path):
    """创建 mock AppContext"""
    root_path = tmp_path / "gui-loader"
    ctx = Mock()
    ctx.paths.audio_path = str(root_path / "audios")
    ctx.paths.hash_path = root_path / "hashes"
    ctx.paths.output_path = str(root_path / "output")
    ctx.config.group_by_type = False
    ctx.config.include_types = ["VO", "SFX", "MUSIC"]
    ctx.config.dev_mode = False
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


def test_resolve_mapping_file_path(mock_app_context):
    """测试映射文件路径解析"""
    expected = Path(mock_app_context.paths.hash_path) / "14.1.0" / "champions" / "1.msgpack"
    with patch("lol_audio_unpack.gui.service.data_loader.find_data_file", return_value=expected) as mock_find:
        actual = resolve_mapping_file_path(mock_app_context, "champions", "1", "14.1.0")

    assert actual == expected
    mock_find.assert_called_once()


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

            with patch("lol_audio_unpack.gui.service.data_loader.check_entity_status", return_value=("已存在", "未存在")), patch(
                "lol_audio_unpack.gui.service.data_loader.resolve_mapping_file_path",
                return_value=None,
            ):
                loader = EntityDataLoader(mock_app_context)
                data = loader.load_entities("champions")

                assert len(data) == 1
                assert data[0]["id"] == "1"
                assert data[0]["name"] == "安妮·黑暗之女"
                assert data[0]["alias"] == "annie"
                assert data[0]["audio"] == "已存在"
                assert data[0]["mapping"] == "未存在"
                assert data[0]["entity_type"] == "champions"
                assert data[0]["mapping_file"] == ""


def test_entity_data_loader_load_mapping_preview(mock_app_context):
    """测试映射预览内容读取"""
    expected_path = Path(mock_app_context.paths.hash_path) / "14.1.0" / "champions" / "1.json"

    with patch("lol_audio_unpack.gui.service.data_loader.DataReader") as mock_reader_cls:
        mock_reader = Mock()
        mock_reader.version = "14.1.0"
        mock_reader_cls.return_value = mock_reader

        with patch(
            "lol_audio_unpack.gui.service.data_loader.resolve_mapping_file_path",
            return_value=expected_path,
        ), patch(
            "lol_audio_unpack.gui.service.data_loader.read_data",
            return_value={"entityName": "安妮", "events": {"VO": {"Play_VO_Annie_Attack": [1, 2, 3]}}},
        ):
            loader = EntityDataLoader(mock_app_context)
            actual_path, content = loader.load_mapping_preview("champions", "1")

    assert actual_path == expected_path
    assert '"entityName": "安妮"' in content
    assert '"Play_VO_Annie_Attack"' in content
