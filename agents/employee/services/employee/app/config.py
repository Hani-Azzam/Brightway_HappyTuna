"""Employee service configuration.

LLM = Anthropic (Claude). Set `ANTHROPIC_API_KEY` (or `EMPLOYEE_ANTHROPIC_API_KEY`
to give the employees their own key); the default model is `claude-haiku-4-5` —
cheap and fast, which is what long simulation runs want. Override with
`EMPLOYEE_ANTHROPIC_MODEL` when a run needs more capability than the personas'
reporting/escalation loop demands.
"""
import os
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas"


class Settings(BaseSettings):
    # --- LLM (Anthropic / Claude) ---
    # Reads EMPLOYEE_ANTHROPIC_API_KEY (env prefix + field name); when that is
    # unset OR empty, falls back to the shared ANTHROPIC_API_KEY so the whole
    # simulation can run off one key in the repo-root .env.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"   # cheap + fast; override for harder runs
    anthropic_max_tokens: int = 4096

    @model_validator(mode="after")
    def _shared_key_fallback(self) -> "Settings":
        if not self.anthropic_api_key:
            self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        return self

    # --- HappyTuna systems the employee acts through ---
    # Internal Chat: reached over REST, identity = Bearer <employee_id>.
    internal_messaging_url: str = "http://localhost:8085"
    # Customer Support: reached over REST (see tools/customer_support_tool.py).
    customer_support_url: str = "http://localhost:8003"

    # --- Activation ---
    # The worker embeds the coordinator, which polls the messaging firehose as this
    # identity (must be registered with a `system`/`coordinator` role → chat:system).
    coordinator_id: str = "COORD-1"
    poll_interval: float = 2.0                     # seconds between activation polls
    # Seconds between customer-support queue sweeps (0 disables them). Each sweep
    # wakes at most one support-capable persona, and only if open tickets exist.
    support_sweep_interval: float = 180.0

    # --- Personas ---
    profiles_dir: str = str(_PERSONAS_DIR)

    model_config = SettingsConfigDict(env_file=".env", env_prefix="EMPLOYEE_", extra="ignore")
