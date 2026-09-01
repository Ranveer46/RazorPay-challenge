"""Thin wrapper around an LLM API, shared by diagnoser (ambiguous root-cause
classification) and composer (message generation). Every call is logged by
the caller into the audit trail — this module only executes calls.

Provider is picked at call time based on whichever key is set:
  - GEMINI_API_KEY    -> Google Gemini (google-genai SDK)
  - ANTHROPIC_API_KEY -> Anthropic Claude
If neither is set, `call()` raises LLMUnavailable so callers fall back to a
deterministic stub — keeps the batch demo runnable fully offline.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# gemini-3.6-flash spends part of max_output_tokens on internal "thinking"
# even at thinking_level="low" — observed ~340 thought tokens for a one-line
# message composition — so a short classification/message budget needs real
# headroom or it comes back empty/truncated. This floor is a max() applied on
# top of whatever the caller asks for; it never shrinks a caller's own budget.
_GEMINI_MIN_OUTPUT_TOKENS = 600

_client = None
_provider = None  # "gemini" | "anthropic"


class LLMUnavailable(RuntimeError):
    pass


def _get_client():
    global _client, _provider
    if _client is not None:
        return _client, _provider

    gemini_key = os.getenv("GEMINI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if gemini_key:
        try:
            from google import genai
        except ImportError as e:
            raise LLMUnavailable(f"google-genai package not installed: {e}")
        _client = genai.Client(api_key=gemini_key)
        _provider = "gemini"
        return _client, _provider

    if anthropic_key:
        try:
            from anthropic import Anthropic
        except ImportError as e:
            raise LLMUnavailable(f"anthropic package not installed: {e}")
        _client = Anthropic(api_key=anthropic_key)
        _provider = "anthropic"
        return _client, _provider

    raise LLMUnavailable("no LLM API key set (GEMINI_API_KEY or ANTHROPIC_API_KEY)")


def call(system: str, user: str, max_tokens: int = 300, model: str | None = None) -> str:
    """Single-turn call. Raises LLMUnavailable if no key/package configured, if
    the provider SDK isn't installed, OR if the live call itself fails for any
    reason (rate limit, network, bad model name, ...). Callers are expected to
    catch LLMUnavailable and fall back to a deterministic stub — a flaky API
    should degrade the message quality for this one event, never crash a
    batch run."""
    client, provider = _get_client()

    try:
        if provider == "gemini":
            from google.genai import types
            resp = client.models.generate_content(
                model=model or DEFAULT_GEMINI_MODEL,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max(max_tokens, _GEMINI_MIN_OUTPUT_TOKENS),
                    thinking_config=types.ThinkingConfig(thinking_level="low"),
                ),
            )
            return (resp.text or "").strip()

        # anthropic
        resp = client.messages.create(
            model=model or DEFAULT_ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [block.text for block in resp.content if getattr(block, "type", None) == "text"]
        return "".join(parts).strip()
    except Exception as e:
        raise LLMUnavailable(f"{provider} call failed: {e}") from e


def is_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))


def active_provider() -> str | None:
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None
