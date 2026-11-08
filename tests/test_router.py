import asyncio

import httpx
import openai
import pytest
from agents import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage

from swc_classroom.router import FailoverModel, KeyRing, Provider


class FakeModel(Model):
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def get_response(self, *args, **kwargs):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def stream_response(self, *args, **kwargs):
        raise AssertionError("Streaming is not used by these tests")


def rate_limit_error():
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://provider.invalid/v1/chat/completions"),
    )
    return openai.RateLimitError("Quota exhausted", response=response, body=None)


@pytest.fixture
def ring(monkeypatch):
    providers = []
    for pid in ("first", "second"):
        key_env = f"SWC_TEST_{pid.upper()}_KEY"
        monkeypatch.setenv(key_env, "test-key")
        providers.append(
            Provider(
                id=pid,
                label=pid.title(),
                kind="grant",
                base_url="https://provider.invalid/v1",
                key_env=key_env,
                model=f"test-{pid}",
                daily_token_budget=100,
                note="Test provider",
            )
        )
    return KeyRing(providers)


@pytest.fixture
def models(monkeypatch, ring):
    models = {
        provider.id: FakeModel(
            ModelResponse(
                output=[],
                usage=Usage(input_tokens=7, output_tokens=4, total_tokens=11),
                response_id=f"response-{provider.id}",
            )
        )
        for provider in ring.providers
    }

    def model_for(self, provider):
        return models[provider.id]

    def forbid_client(self, provider):
        raise AssertionError("Tests must not create provider clients")

    monkeypatch.setattr(KeyRing, "model_for", model_for)
    monkeypatch.setattr(KeyRing, "client", forbid_client)
    return models


def test_rate_limit_fails_over_and_records_events(ring, models):
    models["first"].result = rate_limit_error()
    model = FailoverModel(ring)

    response = asyncio.run(model.get_response())

    assert response is models["second"].result
    assert models["first"].calls == 1
    assert models["second"].calls == 1
    assert [(event.provider, event.outcome) for event in model.events] == [
        ("first", "switched"),
        ("second", "served"),
    ]
    assert model.events[0].detail == "HTTP 429: RateLimitError"
    assert model.events[1].tokens == 11
    assert model.dead == {"first"}
    assert ring.get("first").last_error == "HTTP 429: RateLimitError"
    assert ring.get("first").used_tokens == 0
    assert ring.get("second").used_tokens == 11
    assert ring.get("second").requests == 1


def test_exhausted_provider_stays_dead_across_calls(ring, models):
    model = FailoverModel(ring, exhausted={"first"})

    async def two_calls():
        first = await model.get_response()
        second = await model.get_response()
        return first, second

    responses = asyncio.run(two_calls())

    assert all(response is models["second"].result for response in responses)
    assert models["first"].calls == 0
    assert models["second"].calls == 2
    assert model.dead == {"first"}
    assert [(event.provider, event.outcome) for event in model.events] == [
        ("first", "switched"),
        ("second", "served"),
        ("second", "served"),
    ]
    assert ring.get("first").requests == 0
    assert ring.get("second").used_tokens == 22


@pytest.mark.parametrize("used_tokens", [100, 101])
def test_provider_at_or_over_daily_budget_is_skipped(ring, models, used_tokens):
    ring.get("first").used_tokens = used_tokens
    model = FailoverModel(ring)

    response = asyncio.run(model.get_response())

    assert response is models["second"].result
    assert models["first"].calls == 0
    assert models["second"].calls == 1
    assert model.dead == {"first"}
    assert [(event.provider, event.outcome) for event in model.events] == [
        ("first", "switched"),
        ("second", "served"),
    ]
    assert model.events[0].detail == "school daily budget used up"
    assert ring.get("first").used_tokens == used_tokens


def test_non_failover_exception_propagates(ring, models):
    error = ValueError("Invalid request")
    models["first"].result = error
    model = FailoverModel(ring)

    with pytest.raises(ValueError, match="Invalid request") as caught:
        asyncio.run(model.get_response())

    assert caught.value is error
    assert models["first"].calls == 1
    assert models["second"].calls == 0
    assert model.events == []
    assert model.dead == set()
    assert all(provider.requests == 0 for provider in ring.providers)


def test_all_providers_failing_raises_runtime_error(ring, models):
    for fake in models.values():
        fake.result = rate_limit_error()
    model = FailoverModel(ring)

    with pytest.raises(RuntimeError, match="Every provider on the Key Ring is unavailable"):
        asyncio.run(model.get_response())

    assert all(fake.calls == 1 for fake in models.values())
    assert model.dead == {"first", "second"}
    assert [(event.provider, event.outcome) for event in model.events] == [
        ("first", "switched"),
        ("second", "switched"),
    ]
    assert all(provider.used_tokens == 0 for provider in ring.providers)
    assert all(provider.requests == 0 for provider in ring.providers)


def test_charge_updates_used_tokens(ring):
    provider = ring.get("first")
    provider.used_tokens = 5
    provider.requests = 1
    provider.last_error = "HTTP 429: RateLimitError"

    ring.charge(provider, 11)
    ring.charge(provider, 3)

    assert provider.used_tokens == 19
    assert provider.requests == 3
    assert provider.last_error is None
    assert ring.get("second").used_tokens == 0
    assert ring.get("second").requests == 0
