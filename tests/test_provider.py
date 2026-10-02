import httpx
import pytest

from observatory.providers import CompatibleProvider


def test_remote_provider_requires_opt_in(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    with pytest.raises(ValueError):
        CompatibleProvider()


def test_compatible_response_and_usage(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-only")
    monkeypatch.setenv("LLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("LLM_BASELINE_MODEL", "model-a")

    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Tokyo"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1},
            },
        )

    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = CompatibleProvider().complete({"prompt": "Capital of Japan?"}, "baseline")
    assert result.text == "Tokyo"
    assert result.input_tokens == 10
    assert result.usage_source == "provider"
