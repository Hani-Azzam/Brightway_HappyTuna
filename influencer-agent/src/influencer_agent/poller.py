"""The orchestration loop: poll social_network for new posts, ask the NAT workflow to
decide, act on the decision. This is the only place that sequences the three steps —
everything else in this package is a narrow client for one side of that sequence.
"""

from __future__ import annotations

import asyncio
import logging

from .nat_client import NatWorkflowClient
from .persona import PersonaInstance, load_persona_instance, render_persona_prompt
from .schemas import DecisionRequest
from .social_client import SocialNetworkClient
from .state import PersonaCursor

logger = logging.getLogger(__name__)


class InfluencerPoller:
    def __init__(
        self,
        *,
        social_client: SocialNetworkClient,
        nat_client: NatWorkflowClient,
        cursor: PersonaCursor,
        persona: PersonaInstance,
        persona_prompt: str,
        company_name: str,
        feed_page_size: int,
        poll_interval_seconds: float,
    ) -> None:
        self._social = social_client
        self._nat = nat_client
        self._cursor = cursor
        self._persona = persona
        self._persona_prompt = persona_prompt
        self._company_name = company_name
        self._feed_page_size = feed_page_size
        self._poll_interval_seconds = poll_interval_seconds
        self._bot_user_id: str | None = None
        self._bot_token: str | None = None

    async def start(self) -> None:
        identity = await self._social.login_or_create_bot(self._persona.name, self._persona.account_type)
        self._bot_user_id = identity.user_id
        self._bot_token = identity.token
        logger.info("Logged in as %s (user id %s)", identity.name, identity.user_id)

        while True:
            try:
                await self._poll_once()
            except Exception:
                logger.exception("Poll cycle failed; will retry next interval")
            await asyncio.sleep(self._poll_interval_seconds)

    async def _poll_once(self) -> None:
        new_posts = await self._fetch_new_posts()
        if not new_posts:
            return

        newest_id = new_posts[0]["id"]
        for post in reversed(new_posts):  # oldest-first, so reactions read in publish order
            if post["userId"] == self._bot_user_id:
                continue  # never react to our own posts/reposts
            await self._handle_post(post)

        self._cursor.save_last_seen_post_id(newest_id)

    async def _fetch_new_posts(self) -> list[dict]:
        """Walks the newest-first feed until it hits the last post this persona already saw."""
        last_seen_post_id = self._cursor.load_last_seen_post_id()

        if last_seen_post_id is None:
            # First run ever for this persona: don't react to the entire existing backlog,
            # just record the current newest post as the baseline and react from here on.
            first_page = await self._social.get_feed_page(page=1, limit=self._feed_page_size)
            if first_page:
                self._cursor.save_last_seen_post_id(first_page[0]["id"])
            return []

        new_posts: list[dict] = []
        page = 1

        while True:
            posts = await self._social.get_feed_page(page=page, limit=self._feed_page_size)
            if not posts:
                break

            for post in posts:
                if post["id"] == last_seen_post_id:
                    return new_posts
                new_posts.append(post)

            page += 1

        return new_posts

    async def _handle_post(self, post: dict) -> None:
        request = DecisionRequest(
            persona_prompt=self._persona_prompt,
            post_id=post["id"],
            post_author=post["user"]["name"],
            post_content=post["content"],
            company_name=self._company_name,
        )

        decision = await self._nat.decide(request)
        logger.info("Post %s -> %s (%s)", post["id"], decision.decision, decision.reason)

        if decision.decision == "ignore":
            return

        assert self._bot_token is not None
        await self._social.post_comment(post["id"], self._bot_token, decision.responseText)  # type: ignore[arg-type]

        if decision.decision == "amplify":
            await self._social.repost(post["id"], self._bot_token)
