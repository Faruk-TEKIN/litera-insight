import asyncio
import json

from backend.app.services.ollama_service import OllamaService


class _SyncResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _AsyncStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _AsyncStreamContext:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _AsyncClientStub:
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json):
        self.calls.append(("post", url, json))
        return _SyncResponse({"message": {"content": "hello"}})

    def stream(self, method, url, json):
        self.calls.append(("stream", method, url, json))
        lines = [
            json_module.dumps({"message": {"content": "hel"}}),
            json_module.dumps({"message": {"content": "lo"}}),
        ]
        return _AsyncStreamContext(_AsyncStreamResponse(lines))


json_module = json


def test_chat_generate_sends_system_and_user_messages(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _SyncResponse({"message": {"content": "hello"}})

    monkeypatch.setattr("backend.app.services.ollama_service.requests.post", fake_post)

    service = OllamaService(base_url="http://ollama:11434", model="gemma4:e4b")
    result = service.chat_generate(
        [
            {"role": "system", "content": "system policy"},
            {"role": "user", "content": "user request"},
        ]
    )

    assert result == "hello"
    assert captured["url"] == "http://ollama:11434/api/chat"
    assert captured["timeout"] == 150
    assert captured["json"]["model"] == "gemma4:e4b"
    assert captured["json"]["stream"] is False
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["messages"][1]["role"] == "user"


def test_stream_chat_yields_message_content(monkeypatch):
    monkeypatch.setattr("backend.app.services.ollama_service.httpx.AsyncClient", _AsyncClientStub)

    service = OllamaService(base_url="http://ollama:11434", model="gemma4:e4b")

    async def run():
        chunks = []
        async for chunk in service.stream_chat(
            [
                {"role": "system", "content": "system policy"},
                {"role": "user", "content": "user request"},
            ]
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(run())

    assert chunks == ["hel", "lo"]
