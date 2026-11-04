"""Small synchronous OpenAI-compatible provider for Meta Muse Spark."""

from types import TracebackType
from typing import Self

from openai import APIConnectionError, APIError, APIStatusError, OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam, ChatCompletionToolParam

from backend.agent.config import MetaConfig
from backend.agent.errors import MuseAPIError, MuseConfigurationError


class MuseProvider:
    """Pass messages/tools to Meta and return the SDK completion unchanged.

    Callers supply GridProbe-controlled instructions using the developer role.
    Injected clients are owned by the caller; internally created clients are
    closed by close() or the context manager. No requests occur during setup.
    """

    def __init__(self, config: MetaConfig | None = None, *, client: OpenAI | None = None) -> None:
        self.config = config if config is not None else MetaConfig.from_env()
        self._owns_client = client is None
        if client is not None:
            self._client = client
        else:
            try:
                self._client = OpenAI(
                    api_key=self.config.api_key.get_secret_value(),
                    base_url=self.config.base_url,
                    timeout=60.0,
                    max_retries=0,
                )
            except (ValueError, TypeError):
                raise MuseConfigurationError("Unable to construct the Meta API client; check provider configuration.") from None

    def chat_completion(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        tools: list[ChatCompletionToolParam] | None = None,
    ) -> ChatCompletion:
        """Make one nonstreaming request; never execute returned tool calls."""
        if not messages:
            raise ValueError("At least one message is required.")
        if any(message.get("role") == "system" for message in messages):
            raise ValueError("Use the developer role for GridProbe-controlled instructions.")
        try:
            if tools is None:
                return self._client.chat.completions.create(
                    model=self.config.model, messages=messages, stream=False,
                )
            return self._client.chat.completions.create(
                model=self.config.model, messages=messages, tools=tools, stream=False,
            )
        except APIConnectionError:
            raise MuseAPIError("Meta API connection failed or timed out; check network access.") from None
        except APIStatusError as exc:
            raise MuseAPIError(
                f"Meta API request failed with HTTP {exc.status_code}.", status_code=exc.status_code,
            ) from None
        except APIError:
            raise MuseAPIError("Meta API request failed or returned an invalid response.") from None

    def close(self) -> None:
        """Release the internally created client; leave injected clients open."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
