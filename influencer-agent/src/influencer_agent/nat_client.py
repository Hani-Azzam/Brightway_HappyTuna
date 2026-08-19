"""Calls the NAT workflow that `nat serve` exposes as a local FastAPI endpoint.

The poller never imports NAT internals or the LLM SDKs directly — it only ever sends a
DecisionRequest to POST /generate and gets a DecisionResult back, over plain HTTP. This
keeps "decide" (NAT workflow, LLM-backed) and "act" (poller, social_network HTTP calls)
as two processes that could just as easily run on separate hosts.
"""

from __future__ import annotations

import httpx

from .schemas import DecisionRequest, DecisionResult


class NatWorkflowClient:
    def __init__(self, base_url: str, timeout_seconds: float = 60.0) -> None:
        self._client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def decide(self, request: DecisionRequest) -> DecisionResult:
        response = await self._client.post("/generate", json=request.model_dump())
        response.raise_for_status()
        return DecisionResult.model_validate(response.json())

    async def wait_until_ready(self, attempts: int, delay_seconds: float) -> None:
        import asyncio

        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                response = await self._client.get("/health")
                if response.status_code < 500:
                    return
            except httpx.HTTPError as exc:
                last_error = exc
            await asyncio.sleep(delay_seconds)
        raise RuntimeError(f"NAT workflow server never became ready: {last_error}")
