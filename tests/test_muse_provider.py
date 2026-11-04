"""Offline provider tests: every SDK client constructor/request is mocked."""

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from openai import APIConnectionError, APIError, APIStatusError
from openai.types.chat import ChatCompletion
from pydantic import ValidationError

from backend.agent import provider as provider_module
from backend.agent.config import DEFAULT_META_MODEL, META_BASE_URL, MetaConfig
from backend.agent.errors import MissingMetaAPIKeyError, MuseAPIError, MuseConfigurationError
from backend.agent.provider import MuseProvider


@pytest.fixture(autouse=True)
def sdk_factory(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Isolate credentials and ensure these tests cannot call the real SDK."""
    for variable in ("META_API_KEY", "META_MODEL", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(variable, raising=False)
    factory = MagicMock()
    monkeypatch.setattr(provider_module, "OpenAI", factory)
    return factory


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> MetaConfig:
    # Deliberately fake credential; never used with a real request.
    monkeypatch.setenv("META_API_KEY", "unit-test-placeholder-not-a-real-key")
    return MetaConfig.from_env()


@pytest.fixture
def completion() -> ChatCompletion:
    return ChatCompletion.model_validate({
        "id": "chatcmpl-test", "object": "chat.completion", "created": 1,
        "model": "muse-spark-1.3",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": "GRIDPROBE META OK",
        }}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })


def test_configuration_loading_and_secret_redaction(config: MetaConfig) -> None:
    assert config.model == DEFAULT_META_MODEL == "muse-spark-1.3"
    assert config.base_url == META_BASE_URL == "https://api.meta.ai/v1"
    assert config.api_key.get_secret_value() == "unit-test-placeholder-not-a-real-key"
    assert "api_key" not in config.model_dump()
    assert config.api_key.get_secret_value() not in repr(config)
    assert config.api_key.get_secret_value() not in config.model_dump_json()


def test_model_override(config: MetaConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MODEL", "test-model")
    assert MetaConfig.from_env().model == "test-model"


@pytest.mark.parametrize("key", [None, "", "   ", "\n"])
def test_missing_key(
    monkeypatch: pytest.MonkeyPatch, sdk_factory: MagicMock, key: str | None,
) -> None:
    if key is not None:
        monkeypatch.setenv("META_API_KEY", key)
    # An OpenAI credential must never substitute for META_API_KEY.
    monkeypatch.setenv("OPENAI_API_KEY", "another-fake-test-value")
    with pytest.raises(MissingMetaAPIKeyError, match="Set META_API_KEY"):
        MuseProvider()
    sdk_factory.assert_not_called()


@pytest.mark.parametrize("model", ["", " ", "model with spaces", "model\nname"])
def test_invalid_model_configuration(
    config: MetaConfig, monkeypatch: pytest.MonkeyPatch, model: str,
) -> None:
    monkeypatch.setenv("META_MODEL", model)
    with pytest.raises(MuseConfigurationError, match="Invalid Meta provider configuration") as exc:
        MetaConfig.from_env()
    assert config.api_key.get_secret_value() not in str(exc.value)


@pytest.mark.parametrize("key", ["bad key", "bad\nkey", "bad\tkey", "non-ascii-ğ"])
def test_invalid_key_format(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.setenv("META_API_KEY", key)
    with pytest.raises(MuseConfigurationError) as exc:
        MetaConfig.from_env()
    assert key not in str(exc.value)


def test_invalid_base_url_and_unexpected_config_fields(config: MetaConfig) -> None:
    with pytest.raises(ValidationError):
        MetaConfig(api_key=config.api_key, base_url="https://example.invalid/v1")
    with pytest.raises(ValidationError):
        MetaConfig(api_key=config.api_key, unexpected=True)


def test_client_construction_uses_meta_settings(
    config: MetaConfig, sdk_factory: MagicMock, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "another-fake-test-value")
    with MuseProvider() as provider:
        assert provider.config == config
    sdk_factory.assert_called_once_with(
        api_key=config.api_key.get_secret_value(), base_url="https://api.meta.ai/v1",
        timeout=60.0, max_retries=0,
    )
    sdk_factory.return_value.chat.completions.create.assert_not_called()
    sdk_factory.return_value.close.assert_called_once_with()


def test_client_construction_failure(config: MetaConfig, sdk_factory: MagicMock) -> None:
    sdk_factory.side_effect = ValueError("private SDK error")
    with pytest.raises(MuseConfigurationError, match="Unable to construct"):
        MuseProvider(config)


def test_injected_client_success(
    config: MetaConfig, sdk_factory: MagicMock, completion: ChatCompletion,
) -> None:
    client = MagicMock()
    client.chat.completions.create.return_value = completion
    messages = [
        {"role": "developer", "content": "Return a short response."},
        {"role": "user", "content": "Hello."},
    ]
    with MuseProvider(config, client=client) as provider:
        response = provider.chat_completion(messages)
    assert response is completion
    client.chat.completions.create.assert_called_once_with(
        model="muse-spark-1.3", messages=messages, stream=False,
    )
    assert messages[0]["role"] == "developer"
    assert response.usage.total_tokens == 15
    client.close.assert_not_called()
    sdk_factory.assert_not_called()


def test_completion_uses_configured_model(
    config: MetaConfig, monkeypatch: pytest.MonkeyPatch, sdk_factory: MagicMock,
) -> None:
    monkeypatch.setenv("META_MODEL", "test-model")
    provider = MuseProvider()
    provider.chat_completion([{"role": "user", "content": "Hello."}])
    assert sdk_factory.return_value.chat.completions.create.call_args.kwargs["model"] == "test-model"


def test_tool_call_response_is_returned_without_execution(config: MetaConfig) -> None:
    client = MagicMock()
    completion = ChatCompletion.model_validate({
        "id": "chatcmpl-tools", "object": "chat.completion", "created": 1,
        "model": "muse-spark-1.3",
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "call-test", "type": "function", "function": {
                "name": "test_echo", "arguments": '{"text":"test"}',
            }}],
        }}],
    })
    tools = [{"type": "function", "function": {
        "name": "test_echo", "parameters": {
            "type": "object", "properties": {"text": {"type": "string"}},
        },
    }}]
    messages = [{"role": "user", "content": "Echo test."}]
    client.chat.completions.create.return_value = completion
    response = MuseProvider(config, client=client).chat_completion(messages, tools=tools)
    assert response is completion
    assert response.choices[0].message.tool_calls[0].function.name == "test_echo"
    assert response.choices[0].message.tool_calls[0].function.arguments == '{"text":"test"}'
    client.chat.completions.create.assert_called_once_with(
        model="muse-spark-1.3", messages=messages, tools=tools, stream=False,
    )
    assert client.method_calls == [
        ("chat.completions.create", (), {
            "model": "muse-spark-1.3", "messages": messages, "tools": tools, "stream": False,
        }),
    ]


@pytest.mark.parametrize("messages", [[], [{"role": "system", "content": "Instructions."}]])
def test_message_policy(config: MetaConfig, messages: list[Any]) -> None:
    client = MagicMock()
    with pytest.raises(ValueError):
        MuseProvider(config, client=client).chat_completion(messages)
    client.chat.completions.create.assert_not_called()


def test_network_failure_is_clear_and_redacted(config: MetaConfig) -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = APIConnectionError(
        message=config.api_key.get_secret_value(), request=httpx.Request("POST", META_BASE_URL),
    )
    with pytest.raises(MuseAPIError, match="connection failed or timed out") as exc:
        MuseProvider(config, client=client).chat_completion([{"role": "user", "content": "Hello."}])
    assert config.api_key.get_secret_value() not in str(exc.value)
    assert exc.value.status_code is None


@pytest.mark.parametrize("status", [401, 429, 500])
def test_api_failure_preserves_status_without_body(config: MetaConfig, status: int) -> None:
    client = MagicMock()
    response = httpx.Response(status, request=httpx.Request("POST", META_BASE_URL))
    client.chat.completions.create.side_effect = APIStatusError(
        "private server error", response=response, body={"secret": config.api_key.get_secret_value()},
    )
    with pytest.raises(MuseAPIError, match=f"HTTP {status}") as exc:
        MuseProvider(config, client=client).chat_completion([{"role": "user", "content": "Hello."}])
    assert exc.value.status_code == status
    assert "private server error" not in str(exc.value)
    assert config.api_key.get_secret_value() not in str(exc.value)


def test_other_sdk_failure(config: MetaConfig) -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = APIError(
        "private error", httpx.Request("POST", META_BASE_URL), body=None,
    )
    with pytest.raises(MuseAPIError, match="invalid response"):
        MuseProvider(config, client=client).chat_completion([{"role": "user", "content": "Hello."}])


