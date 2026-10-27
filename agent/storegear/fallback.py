"""Fallback model (decision 2026-10-27, ADR-001 addendum).

The `eu` endpoint of gemini-3.8-flash sometimes hangs and answers 504 after ~12 s, several times in a row (27 Oct:
50 s and 59 s answers, one failed question). Retrying the same endpoint lands on the same overload, so after ONE
failure the call goes to the backup kept in ADR-001: gemini-2.5-flash on europe-west1. Processing stays in the EU.

Only overload and timeouts fall back (5xx, 429, timeouts). A bad request (4xx) is our bug and is raised as is.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Optional

import httpx
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import errors, types

# gemini-2.5 models take a thinking budget, not a thinking level; a small one keeps the backup fast.
FALLBACK_THINKING_BUDGET = 512


def is_overload(e: BaseException) -> bool:
    if isinstance(e, errors.ServerError):
        return True
    if isinstance(e, errors.ClientError):
        return e.code == 429
    return isinstance(e, (httpx.TimeoutException, asyncio.TimeoutError))


class FallbackGemini(Gemini):
    fallback: Optional[Gemini] = None

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        answered = False
        try:
            async for response in super().generate_content_async(llm_request, stream):
                answered = True
                yield response
            return
        except Exception as e:  # noqa: BLE001
            if answered or self.fallback is None or not is_overload(e):
                raise
            print(f"[model] {self.model} failed ({type(e).__name__} {getattr(e, 'code', '')}), "
                  f"falling back to {self.fallback.model}")
        llm_request.model = self.fallback.model
        if llm_request.config:
            llm_request.config.thinking_config = types.ThinkingConfig(thinking_budget=FALLBACK_THINKING_BUDGET)
        async for response in self.fallback.generate_content_async(llm_request, stream):
            yield response
