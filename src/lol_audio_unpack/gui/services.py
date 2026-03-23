"""Temporary GUI preview services.

This module intentionally returns static preview data so the first GUI rollout
can focus on layout and interaction design before wiring Python API callbacks.
"""

from __future__ import annotations

from textwrap import dedent

from .models import GuiPreviewState, MappingPreviewDocument, ResourcePreviewItem


class GuiPreviewService:
    """Provide static preview data for the GUI shell."""

    def load_preview_state(self) -> GuiPreviewState:
        """Build a visually rich preview state.

        Returns:
            A static ``GuiPreviewState`` instance used by the first GUI shell.
        """
        champions = (
            ResourcePreviewItem("1", "Annie", "The Dark Child", "champion", ("VO", "SFX"), "ready"),
            ResourcePreviewItem("103", "Ahri", "The Nine-Tailed Fox", "champion", ("VO", "SFX", "MUSIC"), "cached"),
            ResourcePreviewItem("222", "Jinx", "Loose Cannon", "champion", ("VO", "SFX"), "ready"),
            ResourcePreviewItem("266", "Aatrox", "The Darkin Blade", "champion", ("VO", "SFX", "MUSIC"), "staged"),
            ResourcePreviewItem("350", "Yuumi", "The Magical Cat", "champion", ("VO",), "missing-data"),
            ResourcePreviewItem("777", "Yone", "Unforgotten", "champion", ("VO", "SFX"), "ready"),
        )
        maps_ = (
            ResourcePreviewItem("0", "Common", "Shared banks", "map", ("SFX",), "ready"),
            ResourcePreviewItem("11", "Summoner's Rift", "Classic 5v5", "map", ("VO", "SFX", "MUSIC"), "cached"),
            ResourcePreviewItem("12", "Howling Abyss", "ARAM", "map", ("VO", "SFX", "MUSIC"), "staged"),
            ResourcePreviewItem("30", "Arena", "Round-based mode", "map", ("VO", "SFX"), "queued"),
        )
        logs = (
            "GUI preview shell ready. Python API wiring pending.",
            "Selected backend: direct AppContext + LolAudioUnpackApp integration.",
            "Current mode: layout-first, signals-next.",
            "Mapping viewer is reading static preview data for now.",
        )
        mapping_document = MappingPreviewDocument(
            title="preview-mapping.json",
            content=dedent(
                """
                {
                  "entityType": "champion",
                  "entityId": 103,
                  "entityName": "Ahri",
                  "audioTypes": ["VO", "SFX", "MUSIC"],
                  "files": [
                    {
                      "eventName": "Play_VO_Ahri_Attack",
                      "bank": "vo_ahri_base",
                      "wemId": 48123912,
                      "targetPath": "audios/16.5/champions/103/vo/attack/"
                    },
                    {
                      "eventName": "Play_SFX_Ahri_Orb",
                      "bank": "sfx_ahri_base",
                      "wemId": 48123919,
                      "targetPath": "audios/16.5/champions/103/sfx/orb/"
                    }
                  ]
                }
                """
            ).strip(),
        )
        stats = (
            ("Preview backend", "Python API"),
            ("Ready champions", "4 / 6"),
            ("Ready maps", "3 / 4"),
            ("Next milestone", "signals"),
        )
        return GuiPreviewState(
            champions=champions,
            maps=maps_,
            recent_logs=logs,
            mapping_document=mapping_document,
            hero_stats=stats,
        )
