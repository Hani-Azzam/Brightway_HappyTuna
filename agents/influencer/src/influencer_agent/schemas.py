"""Pydantic contracts shared between the NAT workflow and the poller.

These are the only two shapes that cross the boundary between "decide" (LLM reasoning,
inside NAT) and "act" (HTTP calls to social_network, inside the poller). Keeping them in
one place means the NAT function and the poller can never silently drift apart.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

Decision = Literal["amplify", "criticize", "ignore"]


class DecisionRequest(BaseModel):
    """Input to the NAT workflow: everything it needs to decide, and nothing it doesn't.

    The workflow never touches the social network or the filesystem itself — the poller
    resolves the persona prompt and the post content up front and hands over plain data.
    """

    persona_prompt: str = Field(..., description="Fully rendered system prompt for this influencer persona.")
    post_id: str = Field(..., description="social_network post id, echoed back so the poller can act on it.")
    post_author: str = Field(..., description="Display name of the post's author.")
    post_content: str = Field(..., description="Raw text content of the post.")
    company_name: str = Field(..., description="The company under study (e.g. HappyTuna).")


class DecisionResult(BaseModel):
    """Output of the NAT workflow. Matches the schema requested for this integration."""

    decision: Decision
    reason: str = Field(..., description="Short justification for the decision, grounded in the persona's attributes.")
    responseText: Optional[str] = Field(
        default=None, description="The comment text to publish. Required unless decision is 'ignore'."
    )

    @model_validator(mode="after")
    def _response_text_required_unless_ignore(self) -> "DecisionResult":
        if self.decision != "ignore":
            if not self.responseText or not self.responseText.strip():
                raise ValueError("responseText is required when decision is 'amplify' or 'criticize'")
        return self
