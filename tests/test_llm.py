import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json

from oracle_pageindex.llm import OllamaClient, OllamaError


@pytest.fixture
def client():
    return OllamaClient(base_url="http://localhost:11434", model="llama3.1")


def test_client_init(client):
    assert client.base_url == "http://localhost:11434"
    assert client.model == "llama3.1"


@pytest.mark.asyncio
async def test_chat_async(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "message": {"role": "assistant", "content": "test response"}
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.chat_async("test prompt")
        assert result == "test response"


def test_chat_sync(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "message": {"role": "assistant", "content": "sync response"}
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_response):
        result = client.chat("test prompt")
        assert result == "sync response"


def test_chat_raises_ollama_error_on_max_retries(client):
    with patch("httpx.Client.post", side_effect=ConnectionError("refused")):
        with pytest.raises(OllamaError, match="Max retries"):
            client.chat("test prompt", max_retries=1)


@pytest.mark.asyncio
async def test_chat_async_raises_ollama_error_on_max_retries(client):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock,
               side_effect=ConnectionError("refused")):
        with pytest.raises(OllamaError, match="Max retries"):
            await client.chat_async("test prompt", max_retries=1)


def test_chat_with_finish_info_raises_on_max_retries(client):
    with patch("httpx.Client.post", side_effect=ConnectionError("refused")):
        with pytest.raises(OllamaError, match="Max retries"):
            client.chat_with_finish_info("test prompt", max_retries=1)


def test_maybe_no_think_qwen3():
    qwen_client = OllamaClient(model="qwen3:8b")
    result = qwen_client._maybe_no_think("hello")
    assert result.endswith("/no_think")


def test_maybe_no_think_non_qwen():
    client = OllamaClient(model="llama3.1")
    result = client._maybe_no_think("hello")
    assert "/no_think" not in result


def test_extract_json_from_response(client):
    raw = '```json\n{"key": "value"}\n```'
    result = client.extract_json(raw)
    assert result == {"key": "value"}


def test_extract_json_plain(client):
    raw = '{"key": "value"}'
    result = client.extract_json(raw)
    assert result == {"key": "value"}


def test_extract_json_malformed_returns_empty(client):
    raw = "This is not JSON at all"
    result = client.extract_json(raw)
    assert result == {}


def test_embed_returns_vector(client):
    """embed() calls /api/embed and returns float list."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embeddings": [[0.1, -0.2, 0.3]]}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_response):
        vec = client.embed("Apple Inc.")
    assert isinstance(vec, list)
    assert len(vec) == 3
    assert vec[0] == 0.1


def test_embed_uses_custom_model(client):
    """embed() uses the specified model, not the default chat model."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"embeddings": [[0.1]]}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_response) as mock_post:
        client.embed("test", model="nomic-embed-text")
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["model"] == "nomic-embed-text"


def test_embed_returns_empty_on_error(client):
    """embed() returns empty list on API failure."""
    with patch("httpx.Client.post", side_effect=Exception("connection refused")):
        vec = client.embed("test")
    assert vec == []
