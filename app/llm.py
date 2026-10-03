"""Thin async client for a local Ollama server.

Everything in Rehearsal goes through here, so swapping the open-weight model is
a single environment variable (or one dropdown in the UI) — no code changes.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "gemma2:2b")

# Per-call sampling. Small models get punished for being verbose.
ROLE_OPTIONS = {"temperature": 0.8, "top_p": 0.9, "num_predict": 160}
FEEDBACK_OPTIONS = {"temperature": 0.2, "top_p": 0.9, "num_predict": 180}
SUMMARY_OPTIONS = {"temperature": 0.3, "top_p": 0.9, "num_predict": 220}

# Ollama unloads a model after 5 minutes idle by default. On a laptop GPU the
# reload costs minutes, not seconds, so keep it resident for the session.
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")

# Cold-start bookkeeping. Loading a model into VRAM is slow enough that the
# first user message would otherwise appear to hang, so we pre-warm on startup
# and surface the state to the UI instead of pretending everything is ready.
_warm: dict = {"state": "cold", "model": None, "error": None}


class LLMUnavailable(RuntimeError):
    """Raised when the local Ollama server cannot be reached."""


def warm_status() -> dict:
    return dict(_warm)


def is_warm(model: str | None = None) -> bool:
    return _warm["state"] == "warm" and (model is None or _warm["model"] == model)


async def warm_up(model: str, timeout: float = 900.0) -> bool:
    """Load the model into VRAM ahead of the first real message.

    Runs once at startup as a fire-and-forget task. A failure here is not fatal:
    the app still works, it just falls back to loading on first use.
    """
    _warm.update({"state": "warming", "model": model, "error": None})
    try:
        await generate(
            model,
            "You are a readiness probe. Reply with the single word: ready",
            "Probe.",
            options={"num_predict": 4, "temperature": 0.0},
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — warm-up must never crash the app
        _warm.update({"state": "cold", "error": str(exc)})
        return False
    _warm.update({"state": "warm", "error": None})
    return True


def _client(timeout: float = 120.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=OLLAMA_HOST, timeout=timeout)


async def version() -> str | None:
    try:
        async with _client(timeout=5.0) as client:
            resp = await client.get("/api/version")
            resp.raise_for_status()
            return resp.json().get("version")
    except (httpx.HTTPError, ValueError):
        return None


async def status() -> dict:
    """Health check used by the UI to render an honest offline banner."""
    ollama_version = await version()
    if ollama_version is None:
        return {
            "ready": False,
            "ollama": None,
            "model": DEFAULT_MODEL,
            "models": [],
            "detail": f"Ollama is not responding at {OLLAMA_HOST}.",
        }

    models: list[str] = []
    try:
        async with _client(timeout=10.0) as client:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            models = sorted(m.get("name", "") for m in resp.json().get("models", []))
    except (httpx.HTTPError, ValueError):
        models = []

    warm = warm_status()
    if not models:
        detail = f"Ollama {ollama_version} is running but no models are pulled yet."
    elif warm["state"] == "warming":
        detail = "Warming up the local model — the first reply will be ready shortly."
    elif warm["state"] == "cold" and warm.get("error"):
        detail = f"Model is not loaded yet: {warm['error']}"
    else:
        detail = "Ready."

    return {
        "ready": bool(models),
        "warming": warm["state"] == "warming",
        "warm": warm["state"],
        "ollama": ollama_version,
        "model": DEFAULT_MODEL,
        "models": models,
        "detail": detail,
    }


async def generate(
    model: str,
    system: str,
    prompt: str,
    options: dict | None = None,
    timeout: float = 120.0,
) -> str:
    """One-shot completion. Used for corrections, summaries and the warm-up probe."""
    payload = {
        "model": model,
        "system": system,
        "prompt": prompt,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": options or FEEDBACK_OPTIONS,
    }
    try:
        async with _client(timeout) as client:
            resp = await client.post("/api/generate", json=payload)
            resp.raise_for_status()
            return (resp.json().get("response") or "").strip()
    except httpx.HTTPError as exc:
        raise LLMUnavailable(_friendly(exc)) from exc


async def stream_chat(
    model: str,
    messages: list[dict],
    options: dict | None = None,
) -> AsyncIterator[str]:
    """Stream the conversation partner's reply token by token."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": options or ROLE_OPTIONS,
    }
    try:
        async with _client(timeout=600.0) as client:
            async with client.stream("POST", "/api/chat", json=payload) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    raise LLMUnavailable(
                        f"Ollama returned {resp.status_code}: "
                        f"{resp.text[:200]}"
                    )
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("error"):
                        raise LLMUnavailable(str(data["error"]))
                    chunk = data.get("message", {}).get("content")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
    except httpx.HTTPError as exc:
        raise LLMUnavailable(_friendly(exc)) from exc


def _friendly(exc: Exception) -> str:
    if isinstance(exc, httpx.ConnectError):
        return f"Could not reach Ollama at {OLLAMA_HOST}. Is `ollama serve` running?"
    if isinstance(exc, httpx.ReadTimeout):
        return "The local model timed out. Try a smaller model or a shorter prompt."
    return f"Ollama request failed: {exc}"
