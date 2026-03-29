"""
LLM provider abstraction.

All LangGraph nodes call `get_llm_response()` and `stream_llm_response()` from
this module instead of importing OpenAI directly.  To swap providers, change
LLM_PROVIDER in your .env and install the relevant SDK — no pipeline changes
needed.

Supported providers:
  - openai   (default) — uses OPENAI_API_KEY + optional LLM_BASE_URL for
                          Azure, Ollama, vLLM, or any OpenAI-compatible endpoint
  - anthropic           — requires ANTHROPIC_API_KEY in environment
"""

import logging
import os
from typing import Generator

logger = logging.getLogger(__name__)

_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()


# ---------------------------------------------------------------------------
# Provider: OpenAI (default)
# ---------------------------------------------------------------------------

def _build_openai_client():
    import httpx
    from openai import OpenAI
    from backend.config import OPENAI_API_KEY
    base_url = os.getenv("LLM_BASE_URL") or None   # empty string → None = official endpoint
    return OpenAI(api_key=OPENAI_API_KEY, base_url=base_url)


def _build_anthropic_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _get_client():
    if _PROVIDER == "anthropic":
        return _build_anthropic_client()
    return _build_openai_client()


# Module-level singleton — initialised once per process
_client = None


def _client_singleton():
    global _client
    if _client is None:
        _client = _get_client()
    return _client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_llm_response(prompt: str, temperature: float = 0.5, max_tokens: int = 500) -> str:
    """
    Send a single prompt and return the full text response.
    Works across all supported providers.
    """
    from backend.config import LLM_MODEL
    client = _client_singleton()

    try:
        if _PROVIDER == "anthropic":
            msg = client.messages.create(
                model=LLM_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text.strip()

        # OpenAI (and compatible endpoints)
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"LLM error ({_PROVIDER}): {e}")
        raise


def stream_llm_response(prompt: str, temperature: float = 0.5, max_tokens: int = 500) -> Generator[str, None, None]:
    """
    Yield text tokens one at a time (for SSE streaming).
    Works across all supported providers.
    """
    from backend.config import LLM_MODEL
    client = _client_singleton()

    try:
        if _PROVIDER == "anthropic":
            with client.messages.stream(
                model=LLM_MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for token in stream.text_stream:
                    yield token
            return

        # OpenAI (and compatible endpoints)
        stream = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token

    except Exception as e:
        logger.error(f"LLM streaming error ({_PROVIDER}): {e}")
        raise
