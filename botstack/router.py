"""Key Ring: one school, many model subscriptions and machines.

Every provider speaks the OpenAI Chat Completions protocol, so each one is wrapped
in the Agents SDK's OpenAIChatCompletionsModel. FailoverModel implements the
Agents SDK Model interface and walks the ring in policy order: when a provider is
out of quota, rate limited, down or over the school's daily budget, the turn moves
to the next provider and the switch is recorded for the dashboard.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import openai
from openai import AsyncOpenAI

from agents import ModelResponse
from agents.models.interface import Model
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel


@dataclass
class Provider:
    id: str
    label: str
    kind: str  # "grant" | "free-tier" | "subscription" | "machine"
    base_url: str | None
    key_env: str | None
    model: str
    daily_token_budget: int
    note: str
    used_tokens: int = 0
    requests: int = 0
    last_error: str | None = None

    @property
    def api_key(self) -> str | None:
        if self.key_env is None:
            return "local"
        return os.getenv(self.key_env) or None

    @property
    def configured(self) -> bool:
        if self.kind == "machine":
            return bool(self.base_url)
        return self.api_key is not None

    @property
    def remaining(self) -> int:
        return max(self.daily_token_budget - self.used_tokens, 0)

    def public(self, exhausted: set[str]) -> dict[str, Any]:
        status = "ready"
        if not self.configured:
            status = "offline"
        elif self.id in exhausted or self.remaining == 0:
            status = "exhausted"
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "model": self.model,
            "note": self.note,
            "budget": self.daily_token_budget,
            "used": self.used_tokens,
            "requests": self.requests,
            "status": status,
            "last_error": self.last_error,
        }


def default_ring() -> list[Provider]:
    """Policy order a school admin would set: donated credits first, free tiers next,
    the lab machine last so student work never stops."""
    return [
        Provider(
            id="openai",
            label="OpenAI nonprofit grant",
            kind="grant",
            base_url=os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1",
            key_env="OPENAI_API_KEY",
            model=os.getenv("BOTSTACK_OPENAI_MODEL", "gpt-5.4-mini"),
            daily_token_budget=int(os.getenv("BOTSTACK_OPENAI_BUDGET", "400000")),
            note="Donated OpenAI API credits for the school",
        ),
        Provider(
            id="deepseek",
            label="DeepSeek",
            kind="subscription",
            base_url="https://api.deepseek.com",
            key_env="DEEPSEEK_API_KEY",
            model=os.getenv("BOTSTACK_DEEPSEEK_MODEL", "deepseek-flash"),
            daily_token_budget=int(os.getenv("BOTSTACK_DEEPSEEK_BUDGET", "400000")),
            note="Low-cost subscription the school already pays for",
        ),
        Provider(
            id="gemini",
            label="Gemini free tier",
            kind="free-tier",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            key_env="GEMINI_API_KEY",
            model=os.getenv("BOTSTACK_GEMINI_MODEL", "gemini-2.5-flash"),
            daily_token_budget=int(os.getenv("BOTSTACK_GEMINI_BUDGET", "250000")),
            note="Free daily quota",
        ),
        Provider(
            id="lab-machine",
            label="Library lab Mac (Ollama)",
            kind="machine",
            base_url=os.getenv("BOTSTACK_LAB_URL") or None,
            key_env=None,
            model=os.getenv("BOTSTACK_LAB_MODEL", "llama3.2"),
            daily_token_budget=10_000_000,
            note="Open model on a school computer, no internet quota",
        ),
    ]


class BudgetExhausted(Exception):
    pass


# Errors that mean "this provider cannot take the turn right now".
FAILOVER_STATUS = {401, 402, 403, 404, 408, 409, 429, 500, 502, 503, 504, 529}


def should_fail_over(exc: BaseException) -> bool:
    if isinstance(exc, (BudgetExhausted, openai.APIConnectionError, openai.APITimeoutError)):
        return True
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code in FAILOVER_STATUS
    return False


def describe(exc: BaseException) -> str:
    if isinstance(exc, BudgetExhausted):
        return str(exc)
    if isinstance(exc, openai.APIStatusError):
        return f"HTTP {exc.status_code}: {type(exc).__name__}"
    return type(exc).__name__


class KeyRing:
    """Process-wide ledger of providers and their usage."""

    def __init__(self, providers: list[Provider] | None = None):
        self.providers = providers or default_ring()
        self._lock = threading.Lock()
        self._clients: dict[str, AsyncOpenAI] = {}

    def get(self, pid: str) -> Provider:
        return next(p for p in self.providers if p.id == pid)

    def client(self, p: Provider) -> AsyncOpenAI:
        if p.id not in self._clients:
            self._clients[p.id] = AsyncOpenAI(
                api_key=p.api_key, base_url=p.base_url, max_retries=0, timeout=90
            )
        return self._clients[p.id]

    def model_for(self, p: Provider) -> Model:
        return OpenAIChatCompletionsModel(model=p.model, openai_client=self.client(p))

    def charge(self, p: Provider, tokens: int) -> None:
        with self._lock:
            p.used_tokens += tokens
            p.requests += 1
            p.last_error = None

    def snapshot(self, exhausted: set[str] | None = None) -> list[dict[str, Any]]:
        return [p.public(exhausted or set()) for p in self.providers]

    def reset(self) -> None:
        with self._lock:
            for p in self.providers:
                p.used_tokens = 0
                p.requests = 0
                p.last_error = None


@dataclass
class RouteEvent:
    provider: str
    outcome: str  # "served" | "switched"
    detail: str
    ms: int = 0
    tokens: int = 0

    def public(self) -> dict[str, Any]:
        return self.__dict__.copy()


class FailoverModel(Model):
    """Agents SDK Model that fails over across the Key Ring on every model call."""

    def __init__(self, ring: KeyRing, exhausted: set[str] | None = None, order: list[str] | None = None):
        self.ring = ring
        self.exhausted = exhausted or set()
        self.order = order
        self.events: list[RouteEvent] = []
        # Providers that failed during this run stay skipped for the rest of it.
        self.dead: set[str] = set()

    def __deepcopy__(self, memo: dict) -> "FailoverModel":
        # Agents are cloned per run; the ring and its ledger must stay shared.
        return self

    def _candidates(self) -> list[Provider]:
        ids = self.order or [p.id for p in self.ring.providers]
        return [self.ring.get(i) for i in ids]

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        last: BaseException | None = None
        for p in self._candidates():
            if not p.configured or p.id in self.dead:
                continue
            if p.id in self.exhausted:
                self.dead.add(p.id)
                self.events.append(
                    RouteEvent(p.id, "switched", "HTTP 429: quota exhausted for today")
                )
                continue
            if p.remaining == 0:
                self.dead.add(p.id)
                self.events.append(RouteEvent(p.id, "switched", "school daily budget used up"))
                continue
            started = time.perf_counter()
            try:
                resp = await self.ring.model_for(p).get_response(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - classified below
                if not should_fail_over(exc):
                    raise
                p.last_error = describe(exc)
                self.dead.add(p.id)
                self.events.append(
                    RouteEvent(p.id, "switched", describe(exc), int((time.perf_counter() - started) * 1000))
                )
                last = exc
                continue
            tokens = resp.usage.total_tokens if resp.usage else 0
            self.ring.charge(p, tokens)
            self.events.append(
                RouteEvent(p.id, "served", p.model, int((time.perf_counter() - started) * 1000), tokens)
            )
            return resp
        raise RuntimeError(
            "Every provider on the Key Ring is unavailable"
            + (f" (last error: {describe(last)})" if last else "")
        )

    def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        for p in self._candidates():
            if p.configured and p.id not in self.exhausted and p.remaining > 0:
                return self.ring.model_for(p).stream_response(*args, **kwargs)
        raise RuntimeError("Every provider on the Key Ring is unavailable")
