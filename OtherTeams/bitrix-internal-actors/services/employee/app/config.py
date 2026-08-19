"""Employee service configuration.

LLM = Anthropic (Claude). Set `EMPLOYEE_ANTHROPIC_API_KEY`; the default model is
`claude-haiku-4-5` — cheap and fast, which is what long simulation runs want.
Override with `EMPLOYEE_ANTHROPIC_MODEL` (e.g. `claude-opus-4-8`) when a run
needs more capability than the personas' reporting/escalation loop demands.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PERSONAS_DIR = Path(__file__).resolve().parent.parent / "personas"


class Settings(BaseSettings):
    # --- LLM (Anthropic / Claude) ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"   # override e.g. claude-opus-4-8 for harder runs
    anthropic_max_tokens: int = 4096

    # --- BitriX systems the employee acts through ---
    # Internal Messaging System (v2): reached over REST, identity = Bearer <employee_id>.
    internal_messaging_url: str = "http://localhost:8085"
    mail_url: str = "http://localhost:8082"        # provisional (Team 3)
    portal_url: str = "http://localhost:8083"      # provisional (Team 3)

    # --- Activation ---
    # The worker embeds the coordinator, which polls the messaging firehose as this
    # identity (must be registered with a `system`/`coordinator` role → chat:system).
    coordinator_id: str = "COORD-1"
    poll_interval: float = 2.0                     # seconds between activation polls

    # --- Personas ---
    profiles_dir: str = str(_PERSONAS_DIR)

    model_config = SettingsConfigDict(env_file=".env", env_prefix="EMPLOYEE_", extra="ignore")
