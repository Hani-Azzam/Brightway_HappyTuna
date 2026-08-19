"""Tracks "which posts has this persona already reacted to" across restarts.

social_network's feed has no `since`/`after` filter (see GET /api/posts) — it's page/limit
only, newest-first. So the only way to know what's new is to remember the last post id we
saw and stop paging once we hit it again. One JSON file per persona under STATE_DIR, so it
survives container restarts when that directory is a mounted volume.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


class PersonaCursor:
    def __init__(self, state_dir: Path, persona_handle: str) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        self._path = state_dir / f"{persona_handle}.json"

    def load_last_seen_post_id(self) -> Optional[str]:
        if not self._path.exists():
            return None
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return data.get("last_seen_post_id")

    def save_last_seen_post_id(self, post_id: str) -> None:
        self._path.write_text(json.dumps({"last_seen_post_id": post_id}), encoding="utf-8")
