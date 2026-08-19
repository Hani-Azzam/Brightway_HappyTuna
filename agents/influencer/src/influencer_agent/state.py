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

    def _read(self) -> dict:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def is_baselined(self) -> bool:
        """
        Whether this persona has already decided what counts as "the backlog".

        Distinct from having a post id: a simulation run normally starts against
        an EMPTY feed, and then there is no backlog to skip and no id to
        remember -- but the persona is still baselined, and every post that
        appears from then on is genuinely new. Without this distinction the
        first post of the run would be mistaken for a backlog of one and
        silently skipped.
        """
        data = self._read()
        # `baselined` is absent in files written by older versions; those always
        # carry a real id, which is itself proof of a baseline.
        return bool(data) and bool(data.get("baselined") or data.get("last_seen_post_id"))

    def load_last_seen_post_id(self) -> Optional[str]:
        return self._read().get("last_seen_post_id")

    def save_last_seen_post_id(self, post_id: str) -> None:
        self._write(post_id)

    def baseline_on_empty_feed(self) -> None:
        self._write(None)

    def _write(self, post_id: Optional[str]) -> None:
        self._path.write_text(
            json.dumps({"baselined": True, "last_seen_post_id": post_id}), encoding="utf-8"
        )
