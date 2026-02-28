import json
import sys

import pytest

from lol_audio_unpack.__main__ import parse_arguments


def test_parse_arguments_requires_paths_when_no_config(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["unpack", "hash_table"])
    with pytest.raises(SystemExit):
        parse_arguments()


def test_parse_arguments_with_required_cli_values(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "unpack",
            "--GAME_PATH",
            "/tmp/game",
            "--OUTPUT_PATH",
            "/tmp/out",
            "hash_table",
        ],
    )
    args = parse_arguments()
    assert args["GAME_PATH"] == "/tmp/game"
    assert args["OUTPUT_PATH"] == "/tmp/out"
    assert args["command"] == "hash_table"


def test_parse_arguments_config_file_and_override(monkeypatch, tmp_path):
    config_data = {
        "GAME_PATH": "/from/config/game",
        "OUTPUT_PATH": "/from/config/out",
        "GAME_REGION": "zh_CN",
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "unpack",
            "--config",
            str(config_file),
            "--GAME_REGION",
            "ko_KR",
            "hash_table",
        ],
    )
    args = parse_arguments()
    assert args["GAME_PATH"] == "/from/config/game"
    assert args["OUTPUT_PATH"] == "/from/config/out"
    assert args["GAME_REGION"] == "ko_KR"


def test_parse_arguments_audio_format_requires_vgmstream(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "unpack",
            "--GAME_PATH",
            "/tmp/game",
            "--OUTPUT_PATH",
            "/tmp/out",
            "get_audio",
            "--audio_format",
            "wav",
        ],
    )
    with pytest.raises(SystemExit):
        parse_arguments()
