"""日志初始化行为测试。"""

from __future__ import annotations

from pathlib import Path

import lol_audio_unpack.utils.logging as logging_module


def test_setup_logging_tolerates_missing_stderr_in_windowed_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """当 ``sys.stderr`` 缺失时，日志初始化不应再抛出 ``TypeError``。"""
    add_calls: list[tuple[object, dict[str, object]]] = []

    def fake_add(*args, **kwargs):
        sink = args[0]
        add_calls.append((sink, kwargs))
        if sink is None:
            raise TypeError("Cannot log to objects of type 'NoneType'")
        return 1

    monkeypatch.setattr(logging_module.logger, "add", fake_add)
    monkeypatch.setattr(logging_module.logger, "remove", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(logging_module.sys, "stderr", None)

    logging_module.setup_logging(
        dev_mode=False,
        log_level="INFO",
        file_log_level="DEBUG",
        log_file_path=tmp_path / "logs",
    )

    assert add_calls
    assert callable(add_calls[0][0])
    assert add_calls[1][0] == (tmp_path / "logs" / "{time:YYYY-MM-DD_HH-mm-ss}.log")
