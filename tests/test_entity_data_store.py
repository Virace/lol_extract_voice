from __future__ import annotations

from lol_audio_unpack.gui.controllers.entity_data_store import EntityDataStore


def test_entity_data_store_update_rows_merges_and_preserves_order() -> None:
    store = EntityDataStore(entity_types=("champions", "maps"))
    store.set_rows(
        "champions",
        [
            {"id": "1", "name": "Annie", "audio": "旧"},
            {"id": "103", "name": "Ahri", "audio": "旧"},
        ],
    )

    merged_rows = store.update_rows(
        "champions",
        [
            {"id": "103", "name": "Ahri", "audio": "新"},
            {"id": "222", "name": "Jinx", "audio": "新增"},
        ],
    )

    assert merged_rows == [
        {"id": "1", "name": "Annie", "audio": "旧"},
        {"id": "103", "name": "Ahri", "audio": "新"},
        {"id": "222", "name": "Jinx", "audio": "新增"},
    ]


def test_entity_data_store_clear_resets_all_entity_types() -> None:
    store = EntityDataStore(entity_types=("champions", "maps"))
    store.set_rows("champions", [{"id": "1"}])
    store.set_rows("maps", [{"id": "11"}])

    store.clear()

    assert store.snapshot() == {"champions": [], "maps": []}


def test_entity_data_store_rejects_unknown_entity_type() -> None:
    store = EntityDataStore(entity_types=("champions", "maps"))

    assert store.set_rows("skins", [{"id": "4000"}]) is False
    assert store.update_rows("skins", [{"id": "4000"}]) is None
