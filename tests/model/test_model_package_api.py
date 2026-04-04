"""`model/` 目录包公开导出面测试。"""

from __future__ import annotations

import lol_audio_unpack.model as model_pkg
import lol_audio_unpack.model.entity as model_entity_pkg
from lol_audio_unpack import model as root_model_pkg


def test_root_package_can_import_model_module() -> None:
    """根包应暴露 ``model`` 子模块入口。"""
    assert root_model_pkg is model_pkg


def test_model_package_exports_audio_entity_contract() -> None:
    """`model` 包应暴露稳定的音频实体类型与任务 helper。"""
    assert model_pkg.AudioEntityData is model_entity_pkg.AudioEntityData
    assert callable(model_pkg.AudioEntityData.from_entity)
    assert callable(model_pkg.generate_champion_tasks)
    assert callable(model_pkg.generate_map_tasks)
