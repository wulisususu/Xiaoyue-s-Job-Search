from __future__ import annotations

import json
from typing import Any

import httpx

from ..models import AIProviderConfig
from .errors import ProviderRequestError, ProviderResponseError, ProviderTimeoutError
from .provider import chat_completions_url


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if not lines:
        return stripped
    first = lines[0].strip().lower()
    if first not in {"```", "```json"}:
        return stripped
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


class OpenAICompatibleJSONClient:
    """One transport for every JSON-producing OpenAI-compatible workflow."""

    def __init__(
        self,
        config: AIProviderConfig,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        secret = (api_key or "").strip()
        if not secret:
            raise ValueError("AI provider API key is required")
        self._config = config
        self._api_key = secret
        self._transport = transport

    def complete_json(
        self,
        *,
        messages: list[dict[str, str]],
        schema_name: str,
        schema: dict[str, object],
        max_output_chars: int = 200_000,
    ) -> dict[str, Any]:
        body: dict[str, object] = {
            "model": self._config.text_model,
            "temperature": self._config.temperature,
            "messages": messages,
        }
        if self._config.supports_json_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            }

        try:
            endpoint = chat_completions_url(self._config.base_url)
        except ValueError as exc:
            raise ProviderRequestError(str(exc)) from exc

        try:
            with httpx.Client(
                transport=self._transport,
                timeout=float(self._config.timeout_seconds),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            ) as client:
                response = client.post(endpoint, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("AI provider request timed out") from exc
        except httpx.RequestError as exc:
            raise ProviderRequestError("AI provider request failed") from exc

        if response.status_code >= 400:
            raise ProviderRequestError(f"AI provider returned HTTP {response.status_code}")

        try:
            envelope = response.json()
        except ValueError as exc:
            raise ProviderResponseError("AI provider returned invalid JSON") from exc

        if not isinstance(envelope, dict):
            raise ProviderResponseError("AI provider returned an invalid response")
        choices = envelope.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderResponseError("AI provider response has no completion choice")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ProviderResponseError("AI provider response has no completion message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseError("AI provider response has no completion content")
        if len(content) > max_output_chars:
            raise ProviderResponseError(
                f"AI provider completion exceeds the {max_output_chars}-character output limit"
            )

        try:
            payload = json.loads(_strip_json_fence(content))
        except json.JSONDecodeError as exc:
            raise ProviderResponseError("AI provider completion content is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError("AI provider completion JSON must be an object")
        return payload
