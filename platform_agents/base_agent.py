"""
Shared Gemini agent runtime helpers.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable

from agents import OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from openai import APIStatusError, AsyncOpenAI
from pydantic import BaseModel

from core.env import load_app_env

# Load shared environment variables before the Gemini client is configured.
load_app_env()

# Centralize the Gemini endpoint and model defaults used by all AI agents.
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
)
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    os.getenv("OPENAI_MODEL", "gemini-3.1-flash-lite-preview"),
)


# Resolve the Gemini-compatible API key from the supported env variables.
def gemini_api_key() -> str:
    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY or GOOGLE_API_KEY to use Sentiment Analyzer.")
    return api_key


# Create the shared Gemini chat-completions model wrapper for the agents SDK.
def create_gemini_model() -> OpenAIChatCompletionsModel:
    set_tracing_disabled(True)
    client = AsyncOpenAI(api_key=gemini_api_key(), base_url=GEMINI_BASE_URL)
    return OpenAIChatCompletionsModel(model=GEMINI_MODEL, openai_client=client)


# Run one agents-SDK request asynchronously and coerce the typed output.
async def run_agent_async(agent: object, user_prompt: str, output_type: type[BaseModel]) -> BaseModel:
    result = await Runner.run(agent, user_prompt)
    return result.final_output_as(output_type)


async def _close_agent_client(agent: object) -> None:
    model = getattr(agent, "model", None)
    client = getattr(model, "_client", None)
    close = getattr(client, "close", None)
    if callable(close):
        await close()


# Retry transient Gemini failures before surfacing an error to the caller.
def run_agent(agent_factory: Callable[[], object], user_prompt: str, output_type: type[BaseModel]) -> BaseModel:
    last_exc: Exception | None = None
    for attempt in range(4):
        agent = agent_factory()
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(run_agent_async(agent, user_prompt, output_type))
        except Exception as exc:
            last_exc = exc
            retryable = False
            if isinstance(exc, APIStatusError):
                code = getattr(exc.response, "status_code", None) if exc.response is not None else None
                retryable = code in {429, 500, 502, 503, 504}
            text = str(exc).lower()
            if "high demand" in text or "unavailable" in text or "503" in text:
                retryable = True
            if not retryable or attempt == 3:
                raise
            time.sleep(1.5 * (2**attempt))
        finally:
            try:
                try:
                    loop.run_until_complete(_close_agent_client(agent))
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
            finally:
                asyncio.set_event_loop(None)
                loop.close()
    assert last_exc is not None
    raise last_exc
