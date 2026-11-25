"""Language-model clients. Supports OpenAI-compatible APIs (OpenAI, Groq, OpenRouter, ...) and Google Gemini."""
from __future__ import annotations

import logging
from dataclasses import replace

import httpx

from .config import Settings

log = logging.getLogger("agriassist.llm")


class LLMError(RuntimeError):
    """Raised when the model API cannot be reached or returns an unusable response."""


class BaseLLM:
    name = "base"

    def __init__(self, api_key: str, model: str, timeout: float = 30.0) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError

    def _post(self, url: str, headers: dict, body: dict) -> dict:
        try:
            response = httpx.post(url, headers=headers, json=body, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise LLMError(f"Could not reach the {self.name} API: {exc.__class__.__name__}") from exc
        if response.status_code != 200:
            raise LLMError(f"{self.name} API returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError(f"{self.name} API returned invalid JSON") from exc


class OpenAICompatibleLLM(BaseLLM):
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 30.0) -> None:
        super().__init__(api_key, model, timeout)
        self.base_url = base_url.rstrip("/")

    def complete(self, system: str, user: str) -> str:
        data = self._post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            body={
                "model": self.model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Unexpected response format from the openai-compatible API") from exc


class GeminiLLM(BaseLLM):
    name = "gemini"

    def complete(self, system: str, user: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        data = self._post(
            url,
            headers={"x-goog-api-key": self.api_key},
            body={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.2},
            },
        )
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Unexpected response format from the Gemini API") from exc


DEFAULT_MODELS = {"openai": "gpt-4o-mini", "gemini": "gemini-2.5-flash"}


def build_llm(settings: Settings) -> BaseLLM | None:
    """Return a configured client, or None if no model is set up (retrieval-only mode)."""
    provider = settings.llm_provider
    if provider in ("", "none"):
        return None
    if not settings.llm_api_key:
        log.warning("LLM_PROVIDER=%s but LLM_API_KEY is empty; running without an AI model.", provider)
        return None
    model = settings.llm_model or DEFAULT_MODELS.get(provider, "")
    if provider == "openai":
        return OpenAICompatibleLLM(settings.llm_api_key, model, settings.llm_base_url)
    if provider == "gemini":
        return GeminiLLM(settings.llm_api_key, model)
    log.warning("Unknown LLM_PROVIDER=%s; running without an AI model.", provider)
    return None


def check_connection(llm: BaseLLM | None) -> dict:
    """Send a tiny test request so the user can confirm the API key and model work."""
    if llm is None:
        return {"ok": False, "detail": "No AI model configured. Set LLM_PROVIDER and LLM_API_KEY in backend/.env."}
    try:
        reply = llm.complete("Reply with the single word OK.", "ping")
    except LLMError as exc:
        return {"ok": False, "detail": str(exc), "provider": llm.name, "model": llm.model}
    return {"ok": True, "detail": f"Replied: {reply[:40]}", "provider": llm.name, "model": llm.model}
