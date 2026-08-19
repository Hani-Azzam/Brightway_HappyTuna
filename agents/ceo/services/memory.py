"""Sliding-window memory with summarization for the CEO agent.

The CEO runs as a sequence of independent plan-solve cycles (one per event or
periodic review). Without memory, every cycle starts blind: the CEO re-discovers
the crisis, re-posts similar statements, and cannot follow through on its own
earlier decisions. This module gives cycles continuity:

- The last `window_size` cycles are kept verbatim (situation -> outcome).
- Older cycles are folded into one running summary via a single LLM call at
  eviction time, so memory stays a bounded number of tokens no matter how long
  the simulation runs.
- State persists to a JSON file, so a restarted container resumes with the
  same memory instead of a blank one.

The summarize call is the only LLM usage here, and it happens at most once per
completed cycle (only after the window is full).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage

from services.llm_client import LlmClient

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "ceo_memory.json"

#: Hard cap on the rendered memory block, so a runaway summary can never crowd
#: the planner prompt out of its own context.
MAX_RENDERED_CHARS = 6000


@dataclass
class MemoryConfig:
    window_size: int = 6
    max_outcome_chars: int = 700
    max_summary_words: int = 250
    persist_path: str = field(
        default_factory=lambda: os.environ.get("CEO_MEMORY_PATH", str(_DEFAULT_PATH))
    )


class ConversationMemory:
    """What the CEO remembers between plan-solve cycles."""

    def __init__(self, llm: LlmClient, config: MemoryConfig | None = None) -> None:
        self._llm = llm
        self._config = config or MemoryConfig()
        self._summary: str = ""
        self._recent: list[dict] = []
        self._load()

    # ------------------------------------------------------------------ api

    def add(self, situation: str, outcome: str) -> None:
        """Record one completed cycle and fold anything that falls off the window."""
        self._recent.append({
            "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "situation": situation.strip(),
            "outcome": outcome.strip()[: self._config.max_outcome_chars],
        })
        overflow: list[dict] = []
        while len(self._recent) > self._config.window_size:
            overflow.append(self._recent.pop(0))
        if overflow:
            self._fold(overflow)
        self._save()

    def render(self) -> str:
        """The memory block for the planner prompt. Empty string when blank."""
        if not self._summary and not self._recent:
            return ""
        parts: list[str] = []
        if self._summary:
            parts.append(f"Summary of earlier events and your responses:\n{self._summary}")
        if self._recent:
            lines = []
            for entry in self._recent:
                lines.append(
                    f"- [{entry['when']}] Situation: {entry['situation']}\n"
                    f"  What you did: {entry['outcome']}"
                )
            parts.append("Most recent cycles (newest last):\n" + "\n".join(lines))
        rendered = "\n\n".join(parts)
        if len(rendered) > MAX_RENDERED_CHARS:
            rendered = rendered[-MAX_RENDERED_CHARS:]
        return rendered

    # ------------------------------------------------------------ internals

    def _fold(self, evicted: list[dict]) -> None:
        """One LLM call: merge evicted cycles into the running summary.

        A failed call must not lose the information, so on any error the
        evicted cycles are appended verbatim instead (longer, but complete).
        """
        evicted_text = "\n".join(
            f"- [{e['when']}] Situation: {e['situation']}\n  Response: {e['outcome']}"
            for e in evicted
        )
        prompt = (
            "You maintain the running memory of a company CEO during a crisis "
            "simulation. Merge the existing summary and the new events below into "
            f"ONE updated summary of at most {self._config.max_summary_words} words. "
            "Preserve: the state of the crisis, decisions and public statements "
            "already made, commitments to follow up on, and any ids worth "
            "remembering (tickets, channels). Write plainly, no preamble.\n\n"
            f"EXISTING SUMMARY:\n{self._summary or '(none)'}\n\n"
            f"NEW EVENTS TO MERGE:\n{evicted_text}"
        )
        try:
            self._summary = self._llm.invoke([HumanMessage(content=prompt)]).strip()
        except Exception as exc:  # noqa: BLE001 -- memory must survive an LLM hiccup
            logger.warning("memory summarization failed (%s); keeping verbatim entries", exc)
            self._summary = (self._summary + "\n" + evicted_text).strip()

    def _load(self) -> None:
        path = Path(self._config.persist_path)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._summary = data.get("summary", "")
            self._recent = list(data.get("recent", []))
        except (OSError, ValueError) as exc:
            logger.warning("could not load memory from %s (%s); starting blank", path, exc)

    def _save(self) -> None:
        path = Path(self._config.persist_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"summary": self._summary, "recent": self._recent},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("could not persist memory to %s (%s)", path, exc)
