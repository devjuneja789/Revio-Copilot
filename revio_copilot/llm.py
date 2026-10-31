"""Thin, swappable LLM provider layer (no vendor lock-in, no SDK required for the offline demo).

Providers
- AnthropicProvider      : official `anthropic` SDK (pip install anthropic)
- OpenAICompatProvider   : any OpenAI-compatible /chat/completions endpoint using plain `requests`
                           (OpenAI, Groq, OpenRouter, Gemini's OpenAI-compat endpoint, a local Ollama...)
- ScriptedProvider       : deterministic fake used by the tests

NOTE: the live providers are exercised in this repo only through unit tests with fake transports;
they have not been run against a real API key by the author. See README "Known limitations".
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional, Protocol


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str, *, json_mode: bool = False, max_tokens: int = 700) -> str: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise LLMError("pip install anthropic to use AnthropicProvider") from e
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model or os.getenv("REVIO_MODEL", "claude-sonnet-5-5")

    def complete(self, system: str, user: str, *, json_mode: bool = False, max_tokens: int = 700) -> str:
        try:
            msg = self._client.messages.create(
                model=self.model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": user}]
            )
        except Exception as e:  # network / auth / rate limit
            raise LLMError(f"anthropic call failed: {e}") from e
        return "".join(getattr(b, "text", "") for b in msg.content)


class OpenAICompatProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, session=None, timeout: int = 40):
        import requests

        self.base_url, self.api_key, self.model, self.timeout = base_url.rstrip("/"), api_key, model, timeout
        self._http = session or requests.Session()

    def complete(self, system: str, user: str, *, json_mode: bool = False, max_tokens: int = 700) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if json_mode and os.getenv("REVIO_JSON_MODE", "1") == "1":
            payload["response_format"] = {"type": "json_object"}
        try:
            r = self._http.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise LLMError(f"openai-compatible call failed: {e}") from e


class ScriptedProvider:
    """Returns queued responses in order; records every call. For tests and offline demos of the LLM path."""

    name = "scripted"

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def complete(self, system: str, user: str, *, json_mode: bool = False, max_tokens: int = 700) -> str:
        self.calls.append({"system": system, "user": user, "json_mode": json_mode})
        if not self.responses:
            raise LLMError("ScriptedProvider exhausted")
        return self.responses.pop(0)


def provider_from_env() -> Optional[LLMProvider]:
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    if os.getenv("REVIO_BASE_URL") and os.getenv("REVIO_API_KEY"):
        return OpenAICompatProvider(os.environ["REVIO_BASE_URL"], os.environ["REVIO_API_KEY"], os.getenv("REVIO_MODEL", "gpt-4o-mini"))
    return None


def extract_json(text: str) -> dict:
    """Tolerant JSON extraction: strips code fences/preamble and returns the first balanced object."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    if start < 0:
        raise LLMError("no JSON object in model output")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[start : i + 1])
                except json.JSONDecodeError as e:
                    raise LLMError(f"invalid JSON from model: {e}") from e
    raise LLMError("unterminated JSON object in model output")
