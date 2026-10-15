import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parent.parent / "services/ai_providers/openai_format.py"
TOOL = {
    "name": "categorize_transactions",
    "description": "Suggest accounts for Alder Lantern Studio",
    "input_schema": {"type": "object", "properties": {"suggestions": {"type": "array"}}},
}


@pytest.fixture
def openai_module(monkeypatch):
    package = ModuleType("sweep_ai_providers")
    package.__path__ = []
    validated_urls = []
    package.validate_provider_url = lambda spec, url: validated_urls.append((spec, url))
    monkeypatch.setitem(sys.modules, package.__name__, package)
    path = Path(os.environ.get("SWEEP_MUTANT_FILE", SOURCE))
    spec = importlib.util.spec_from_file_location(
        "sweep_ai_providers.openai_format", path
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module, validated_urls


def make_request(module):
    provider = SimpleNamespace(base_url="https://api.openai.com/v1", model="gpt-5-mini")
    return module.OpenAIRequest(provider, "offline-key", TOOL, "Categorize 2026-03-12 fee of 18.25")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def response(arguments, second_arguments=None):
    calls = [{"function": {"arguments": arguments}}]
    if second_arguments is not None:
        calls.append({"function": {"arguments": second_arguments}})
    return {"choices": [{"message": {"tool_calls": calls}}]}


class TestOpenAIRequestInit:
    def test_keeps_constructor_inputs(self, openai_module):
        module, _ = openai_module
        request = make_request(module)

        assert request.spec.base_url == "https://api.openai.com/v1"
        assert request.api_key == "offline-key"
        assert request.tool is TOOL
        assert request.prompt == "Categorize 2026-03-12 fee of 18.25"


class TestOpenAIRequestUrl:
    def test_appends_chat_completions_to_base_url(self, openai_module):
        module, _ = openai_module

        assert make_request(module).url == "https://api.openai.com/v1/chat/completions"


class TestOpenAIRequestPayload:
    def test_uses_tool_schema_and_forces_named_tool(self, openai_module):
        module, _ = openai_module
        request = make_request(module)

        assert request.payload() == {
            "model": "gpt-5-mini",
            "max_tokens": 4000,
            "tools": [{"type": "function", "function": {
                "name": "categorize_transactions",
                "description": "Suggest accounts for Alder Lantern Studio",
                "parameters": TOOL["input_schema"],
            }}],
            "tool_choice": {
                "type": "function", "function": {"name": "categorize_transactions"}
            },
            "messages": [{"role": "user", "content": "Categorize 2026-03-12 fee of 18.25"}],
        }


class TestOpenAIRequestSend:
    def test_posts_json_with_authentication_and_timeout(self, openai_module, monkeypatch):
        module, validated_urls = openai_module
        request = make_request(module)
        calls = []

        def fake_urlopen(http_request, timeout):
            calls.append((http_request, timeout))
            return FakeResponse(response('{"suggestions":[{"index":1,"account_number":"6510"}]}'))

        monkeypatch.setattr(module, "urlopen", fake_urlopen)

        assert request.send() == [{"index": 1, "account_number": "6510"}]
        assert validated_urls == [(request.spec, request.url)]
        assert len(calls) == 1
        http_request, timeout = calls[0]
        assert http_request.full_url == request.url
        assert http_request.get_method() == "POST"
        assert http_request.get_header("Authorization") == "Bearer offline-key"
        assert http_request.get_header("Content-type") == "application/json"
        assert json.loads(http_request.data.decode("utf-8")) == request.payload()
        assert timeout == 60

    def test_reads_first_choice_and_first_tool_call(self, openai_module, monkeypatch):
        module, _ = openai_module
        first = {"suggestions": [{"index": 1, "account_number": "6510"}]}
        second = {"suggestions": [{"index": 2, "account_number": "7520"}]}
        payload = {"choices": [
            {"message": {"tool_calls": [
                {"function": {"arguments": first}},
                {"function": {"arguments": second}},
            ]}},
            {"message": {"tool_calls": [{"function": {"arguments": second}}]}},
        ]}
        monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: FakeResponse(payload))

        assert make_request(module).send() == first["suggestions"]

    def test_accepts_object_arguments_and_missing_suggestions(self, openai_module, monkeypatch):
        module, _ = openai_module
        monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: FakeResponse(response({})))

        assert make_request(module).send() == []

    @pytest.mark.parametrize("payload", [
        {"choices": []},
        {"choices": [{"message": {"tool_calls": []}}]},
        response("{invalid json"),
    ])
    def test_rejects_missing_or_invalid_tool_call(self, openai_module, monkeypatch, payload):
        module, _ = openai_module
        monkeypatch.setattr(module, "urlopen", lambda *args, **kwargs: FakeResponse(payload))

        with pytest.raises(ValueError, match="valid categorize_transactions tool call"):
            make_request(module).send()
