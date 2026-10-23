import io
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi import HTTPException
from PIL import Image

from app import ai


@pytest.fixture
def picture():
    stream = io.BytesIO()
    Image.new("RGB", (80, 40), "white").save(stream, "PNG")
    return stream.getvalue()


@pytest.fixture
def fields():
    return {name: "" for name in ai.ExtractedFields.model_fields} | {"name": "Example"}


def mock_client(monkeypatch, *, fields=None, error=None, truncated=False):
    async def create(**kwargs):
        assert kwargs["tool_choice"]["name"] == "extract_business_card"
        assert kwargs["messages"][0]["content"][0]["type"] == "image"
        if error is not None:
            raise error
        return SimpleNamespace(
            stop_reason="max_tokens" if truncated else "tool_use",
            content=[SimpleNamespace(type="tool_use", name="extract_business_card", input=fields)],
        )

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.messages = SimpleNamespace(create=create)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "synthetic-test-model")
    monkeypatch.setenv("AI_EXTRACT_TIMEOUT_SECONDS", "5")
    monkeypatch.setattr(ai.anthropic, "AsyncAnthropic", Client)


def execute(picture):
    import asyncio
    return asyncio.run(ai.extract_fields(picture, "image/png"))


def test_ai_requires_configuration(monkeypatch, picture):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    with pytest.raises(HTTPException) as result:
        execute(picture)
    assert result.value.status_code == 503


def test_ai_transcription_normalizes_null_without_guessing(monkeypatch, picture, fields):
    fields["phone"] = None
    fields["name"] = " Example "
    mock_client(monkeypatch, fields=fields)
    result = execute(picture)
    assert result["name"] == "Example"
    assert result["phone"] == ""
    assert set(result) == set(ai.ExtractedFields.model_fields)


@pytest.mark.parametrize("invalid", ["extra", "missing", "wrong_type", "too_long"])
def test_invalid_ai_output_rejected(monkeypatch, picture, fields, invalid):
    if invalid == "extra":
        fields["role"] = "admin"
    elif invalid == "missing":
        fields.pop("address")
    elif invalid == "wrong_type":
        fields["name"] = {"text": "Example"}
    else:
        fields["name"] = "x" * 201
    mock_client(monkeypatch, fields=fields)
    with pytest.raises(HTTPException) as result:
        execute(picture)
    assert result.value.status_code == 502
    assert result.value.detail["code"] == "ai_invalid_response"


def test_truncated_output_rejected(monkeypatch, picture, fields):
    mock_client(monkeypatch, fields=fields, truncated=True)
    with pytest.raises(HTTPException) as result:
        execute(picture)
    assert result.value.status_code == 502


@pytest.mark.parametrize("kind,status", [("timeout", 504), ("authentication", 502), ("rate", 502), ("connection", 502)])
def test_sdk_errors_are_safe(monkeypatch, picture, kind, status):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(401, request=request)
    secret = "private-image-and-key-content"
    if kind == "timeout":
        error = anthropic.APITimeoutError(request=request)
    elif kind == "authentication":
        error = anthropic.AuthenticationError(secret, response=response, body={"secret": secret})
    elif kind == "rate":
        error = anthropic.RateLimitError(secret, response=response, body={"secret": secret})
    else:
        error = anthropic.APIConnectionError(message=secret, request=request)
    mock_client(monkeypatch, error=error)
    with pytest.raises(HTTPException) as result:
        execute(picture)
    assert result.value.status_code == status
    assert secret not in str(result.value.detail)


def test_ai_resize_preserves_input():
    stream = io.BytesIO()
    Image.new("RGB", (3000, 1000), "white").save(stream, "PNG")
    original = stream.getvalue()
    prepared, mime = ai.prepare_image(original, "image/png")
    assert mime == "image/png"
    assert Image.open(io.BytesIO(prepared)).size == (1568, 523)
    assert Image.open(io.BytesIO(original)).size == (3000, 1000)
