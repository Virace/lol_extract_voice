"""大厅音频的固定文件名与本地语言归属。"""

from pathlib import Path

LOBBY_FILES = {
    "champion-ban-vo": "ban.ogg",
    "champion-choose-vo": "choose.ogg",
    "champion-sfx-audios": "sfx.ogg",
}


def find_lobby_source(manifest: Path, region: str, champion_id: str, category: str) -> Path | None:
    """定位指定版本 manifest 内的大厅文件，不跨语言回退。"""
    if category == "champion-sfx-audios" or region.lower() in {"default", "en_us"}:
        regions = ("default",)
    else:
        regions = (region, region.lower())
    return next(
        (
            path
            for language in regions
            if (path := manifest / "lobby" / language / category / f"{champion_id}.ogg").is_file()
        ),
        None,
    )
