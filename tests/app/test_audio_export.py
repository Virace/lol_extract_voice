"""验证额外 WAV 根目录保留正式输出的版本、语言和实体归属。"""

from pathlib import Path

import pytest

from lol_audio_unpack.app.audio_export import AudioExportRequest, ExportTarget
from lol_audio_unpack.app.audio_scope import AudioScope
from lol_audio_unpack.app.types import WavOutputOptions
from lol_audio_unpack.runtime.wav import build_output_path

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("version", "region", "files"),
    [
        ("16.18", "zh_CN", ("champions/1·Annie·安妮/1000·基础/VO/123.wem",)),
        ("16.19", "ja_JP", ("champions/1·Annie·安妮/1001·哥特萝莉/VO/123.wem",)),
        (
            "16.18",
            "en_US",
            (
                "VO/champions/1·Annie·安妮/1000·基础/123.wem",
                "SFX/champions/1·Annie·安妮/1000·基础/123.wem",
                "champions/1·Annie·安妮/lobby/choose.ogg",
            ),
        ),
    ],
)
def test_extra_wav_root_keeps_full_layout(tmp_path: Path, version: str, region: str, files: tuple[str, ...]) -> None:
    """额外根替代 wavs，单个与多个类型范围都保留版本、语言及完整实体路径。"""
    root = tmp_path / "audios" / version / region
    scopes = tuple(AudioScope(root / Path(file).parent, files=(Path(file).name,)) for file in files)
    request = AudioExportRequest(
        entity_type="champions",
        entity_id="1",
        entity_name="安妮",
        version=version,
        version_root=root,
        targets=tuple(ExportTarget(scope, tmp_path / "wavs") for scope in scopes),
        report_root=tmp_path / "reports",
        options=WavOutputOptions(enabled=True),
        region=region,
    )
    output = tmp_path / "selected-wavs"

    targets = request.build_targets(scopes, output)
    outputs = tuple(
        build_output_path(root / file, audio_root=target.scope.root, wav_root=target.output_root)
        for file, target in zip(files, targets, strict=True)
    )

    assert outputs == tuple(output / version / region / Path(file).with_suffix(".wav") for file in files)
