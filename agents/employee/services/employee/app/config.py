"""Employee service configuration.

LLM = Anthropic (Claude). Set `ANTHROPIC_API_KEY` (or `EMPLOYEE_ANTHROPIC_API_KEY`
to give the employees their own key); the default model is `claude-haiku-4-5` —
cheap and fast, which is what long simulation runs want. Override with
`EMPLOYEE_ANTHROPIC_MODEL` when a run needs more capability than the personas'
reporting/escalation loop demands.
"""
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas"


class Settings(BaseSettings):
    # --- LLM (Anthropic / Claude) ---
    # The employee-specific name wins when both are set; the plain one lets the
    # whole simulation share a single key in the repo-root .env.
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("EMPLOYEE_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    anthropic_model: str = "claude-haiku-4-5"   # cheap + fast; override for harder runs
    anthropic_max_tokens: int = 4096

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
