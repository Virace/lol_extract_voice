"""旧输出一次性迁移、硬链接去重与中断继续的行为验证。"""

import json
from pathlib import Path

import msgpack
import pytest
from ruamel.yaml import YAML

from lol_audio_unpack.app import context
from lol_audio_unpack.app.artifacts import enumerate_audio_refs
from lol_audio_unpack.app.lobby import repair_lobby
from lol_audio_unpack.app.migration import migrate_library
from lol_audio_unpack.app.resource_pack import build_resource_pack_key, resource_pack_path_component
from lol_audio_unpack.manager.data_updater import DataUpdater
from lol_audio_unpack.manager.files import read_data, write_data
from lol_audio_unpack.manager.lobby import LOBBY_FILES
from lol_audio_unpack.model import AudioEntityData
from lol_audio_unpack.runtime.library import Library, LibraryError
from tests.factories import make_context, make_wav

pytestmark = pytest.mark.integration
VERSION = "16.18"
SKIN = "1000·基础皮肤"
FOLDER = "1·Annie·安妮"
MEDIA_ID = 101


def make_old(root: Path, *, grouped=False, suffix=".msgpack"):
    """建立两个原 ID、相同内容的旧 WEM，并保留已有映射和 WAV。"""
    manifest = root / "manifest" / VERSION
    manifest.mkdir(parents=True)
    catalog = {
        "metadata": {"scriptName": "lol-audio-unpack", "gameVersion": VERSION, "languages": ["default", "zh_CN"]},
        "champions": {"1": {"alias": "Annie", "name": "安妮"}},
        "maps": {},
    }
    marker = manifest / f"data{suffix}"
    if suffix == ".msgpack":
        marker.write_bytes(msgpack.packb(catalog, use_bin_type=True))
    elif suffix == ".json":
        marker.write_text(json.dumps(catalog), encoding="utf-8")
    else:
        with marker.open("w", encoding="utf-8") as stream:
            YAML().dump(catalog, stream)
    body = Path("VO") / "champions" / FOLDER / SKIN if grouped else Path("champions") / FOLDER / SKIN / "VO"
    sources = []
    for number in (101, 102):
        path = root / "audios" / VERSION / body / f"{number}.wem"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"same actual bytes")
        sources.append(path)
    empty = root / "audios" / VERSION / "champions/2·Olaf·奥拉夫/2000·基础皮肤/VO"
    empty.mkdir(parents=True)
    wav = root / "wavs" / VERSION / body / "101.wav"
    wav.parent.mkdir(parents=True)
    wav.write_bytes(make_wav())
    relative = f"VO/{SKIN}/101.wem" if grouped else f"{SKIN}/VO/101.wem"
    mapping = {"skins": {"1000": {"events": {"VOICE": {"Play": [101]}}, "audioPaths": {"VOICE": {"Play": [relative]}}}}}
    write_data(mapping, root / "hashes" / VERSION / "champions/1")
    return sources, wav, marker, body, mapping


@pytest.mark.parametrize("grouped", [False, True])
@pytest.mark.parametrize("suffix", [".msgpack", ".json", ".yaml"])
def test_migration_moves_media_without_copying_or_game_source(tmp_path, grouped, suffix):
    """两种目录和旧数据格式一次搬完；重复字节只留一份，普通读取只消费新库。"""
    sources, wav, marker, body, mapping = make_old(tmp_path, grouped=grouped, suffix=suffix)
    inode, wav_inode = sources[0].stat().st_ino, wav.stat().st_ino
    progress = []
    migrate_library(tmp_path, progress_callback=progress.append)
    library = Library(tmp_path)
    index = library.load(VERSION, "zh_CN")
    refs = list(index.iter_media())
    assert {ref.media_id for ref in refs} == {101, 102}
    assert len(list((tmp_path / "audios/_data").rglob("*.wem"))) == 1
    new = tmp_path / "audios" / VERSION / "zh_CN" / body
    obj = library.locate(refs[0].object)
    assert obj.stat().st_ino == inode
    assert (new / "101.wem").samefile(obj) and (new / "102.wem").samefile(obj)
    assert (tmp_path / "wavs" / VERSION / "zh_CN" / body / "101.wav").stat().st_ino == wav_inode
    assert not marker.exists() and not any(path.exists() for path in [*sources, wav])
    assert sorted(path.name for path in (tmp_path / "audios" / VERSION).iterdir()) == ["zh_CN"]
    assert read_data(tmp_path / "hashes" / VERSION / "zh_CN/champions/1") == mapping
    assert set(index.to_dict()) == {
        "schema",
        "version",
        "algorithm",
        "region",
        "champions",
        "maps",
        "resource_packs",
        "wavs",
    }
    assert not (tmp_path / "wavs/_data").exists()
    entity = AudioEntityData("1", "安妮", "Annie", None, "champion", {"1000": {"name": "基础皮肤"}}, "")
    ctx = make_context(tmp_path, group_by_type=grouped)
    assert len(enumerate_audio_refs(ctx, entity, VERSION)) == len(sources)
    assert progress[0].event == "started" and progress[-1].event == "finished"
    before = library.resolve(index.path).stat().st_mtime_ns
    migrate_library(tmp_path)
    assert library.resolve(index.path).stat().st_mtime_ns == before


@pytest.mark.parametrize("stage", ["index", "cleanup"])
def test_migration_restarts_from_original_marker_after_interruption(tmp_path, monkeypatch, stage):
    """索引或清理中断都可继续，无需事务框架、重复解包或媒体副本。"""
    sources, _, marker, body, _ = make_old(tmp_path)
    original_merge, original_unlink = Library.merge, Path.unlink
    if stage == "index":
        monkeypatch.setattr(Library, "merge", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("index full")))
    else:

        def unlink(path, *args, **kwargs):
            if path == sources[1]:
                raise OSError("file busy")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(OSError):
        migrate_library(tmp_path)
    assert marker.is_file() and sources[1].is_file()
    assert (tmp_path / "audios" / VERSION / "zh_CN" / body / "102.wem").is_file()
    monkeypatch.setattr(Library, "merge", original_merge)
    monkeypatch.setattr(Path, "unlink", original_unlink)
    migrate_library(tmp_path)
    assert not marker.exists() and not sources[1].exists()
    assert {ref.media_id for ref in Library(tmp_path).load(VERSION, "zh_CN").iter_media()} == {101, 102}


def test_existing_different_target_stops_before_moving_old_files(tmp_path):
    """新旧目录同名目标不同内容时拒绝覆盖，也不删除旧数据。"""
    sources, _, marker, body, _ = make_old(tmp_path)
    target = tmp_path / "audios" / VERSION / "zh_CN" / body / "101.wem"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"new content")
    with pytest.raises(LibraryError, match="不同内容"):
        migrate_library(tmp_path)
    assert marker.exists() and all(path.exists() for path in sources)
    assert target.read_bytes() == b"new content"
    assert not (tmp_path / "audios/_data").exists()


def test_context_migrates_before_new_source_operations(tmp_path, monkeypatch):
    """所有正式入口共用上下文迁移门禁；迁移后无需旧目录读取分支。"""
    sources, _, marker, _, _ = make_old(tmp_path)

    def validate(_game_path):
        assert not marker.exists() and not any(path.exists() for path in sources)

    monkeypatch.setattr(context, "validate_local_source", validate)
    ctx = context.create_app_context(settings={"OUTPUT_PATH": str(tmp_path), "GAME_PATH": str(tmp_path / "game")})
    assert ctx.version_path("manifest", VERSION).joinpath("data.msgpack").is_file()


@pytest.mark.parametrize("current", [False, True])
def test_missing_lobby_is_repaired_after_migration(tmp_path, monkeypatch, current):
    """迁移缺项从同版本源补齐；历史版本不读当前客户端，已有文件不被替换。"""
    make_old(tmp_path)
    old_ban = tmp_path / "audios" / VERSION / "champions" / FOLDER / "lobby/ban.ogg"
    old_ban.parent.mkdir(parents=True)
    old_ban.write_bytes(b"original ban")
    migrate_library(tmp_path)
    ctx = make_context(tmp_path, runtime_cache={"resolved_runtime_version": VERSION if current else "16.19"})
    prepared = []

    def prepare(updater, ids):
        prepared.extend(ids)
        for category, name in LOBBY_FILES.items():
            language = "default" if name == "sfx.ogg" else "zh_CN"
            path = tmp_path / "manifest" / VERSION / "zh_CN/lobby" / language / category / "1.ogg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())

    monkeypatch.setattr(DataUpdater, "ensure_lobby_audio", prepare)
    if not current:
        prepare(None, ())
    repair_lobby(ctx)
    target = tmp_path / "audios" / VERSION / "zh_CN/champions" / FOLDER / "lobby"
    assert (target / "ban.ogg").read_bytes() == b"original ban"
    assert (target / "choose.ogg").read_bytes() == b"choose.ogg"
    assert (target / "sfx.ogg").read_bytes() == b"sfx.ogg"
    assert prepared == (["1"] if current else [])
    entity = AudioEntityData("1", "安妮", "Annie", None, "champion", {}, "")
    assert {ref.path.name for ref in enumerate_audio_refs(ctx, entity, VERSION)} == {
        "101.wem",
        "102.wem",
        "ban.ogg",
        "choose.ogg",
        "sfx.ogg",
    }
    assert not list((tmp_path / "audios/_data").rglob("*.ogg"))
    before = (target / "choose.ogg").stat().st_mtime_ns
    repair_lobby(ctx)
    assert (target / "choose.ogg").stat().st_mtime_ns == before
    assert prepared == (["1"] if current else [])


@pytest.mark.parametrize("grouped", [False, True])
def test_map_and_resource_pack_keep_original_identity(tmp_path, grouped):
    """地图与显式资源包不增加皮肤层，英语旧库及跨实体相同内容一并迁移。"""
    catalog = {"metadata": {"scriptName": "lol-audio-unpack", "gameVersion": VERSION, "languages": []}}
    write_data(catalog, tmp_path / "manifest" / VERSION / "data")
    pack = build_resource_pack_key("TFTCommon.wad.client", "MODE_TFT_NPC_ElderDragon_SFX")
    for group, folder in (
        ("maps", "11·SR·召唤师峡谷"),
        ("resource_packs", f"{resource_pack_path_component(pack)}·dragon·巨龙"),
    ):
        body = Path("SFX") / group / folder if grouped else Path(group) / folder / "SFX"
        path = tmp_path / "audios" / VERSION / body / "101.wem"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"shared")
    migrate_library(tmp_path)
    library = Library(tmp_path)
    refs = list(library.load(VERSION, "en_US").iter_media())
    assert {(ref.entity_type, ref.entity_id) for ref in refs} == {
        ("map", "11"),
        ("resource_pack", pack),
    }
    assert len({library.locate(ref.object) for ref in refs}) == 1
    assert list((tmp_path / "audios" / VERSION).iterdir()) == [tmp_path / "audios" / VERSION / "en_US"]
