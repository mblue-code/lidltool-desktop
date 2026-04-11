from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class CodexOAuthTextResponse:
    text: str
    latency_ms: int
    usage: dict[str, int]


def chatgpt_account_id_from_bearer(bearer_token: str) -> str:
    try:
        jwt_parts = bearer_token.split(".")
        payload = json.loads(base64.urlsafe_b64decode(jwt_parts[1] + "=="))
    except Exception:  # noqa: BLE001
        return ""
    return str(payload.get("sub") or "")


def complete_text_with_codex_oauth(
    *,
    bearer_token: str,
    model: str,
    instructions: str,
    input_items: list[dict[str, Any]],
    timeout_s: float = 120.0,
) -> CodexOAuthTextResponse:
    normalized_token = bearer_token.strip()
    if not normalized_token:
        raise RuntimeError("ChatGPT Codex OAuth bearer token is required")

    normalized_model = model.strip()
    if not normalized_model:
        raise RuntimeError("ChatGPT Codex OAuth model is required")

    request_body = {
        "model": normalized_model,
        "instructions": instructions,
        "input": input_items,
        "store": False,
        "stream": True,
    }
    account_id = chatgpt_account_id_from_bearer(normalized_token)
    text_parts: list[str] = []
    usage: dict[str, int] = {}
    started = time.perf_counter()

    with httpx.stream(
        "POST",
        "https://chatgpt.com/backend-api/codex/responses",
        headers={
            "Authorization": f"Bearer {normalized_token}",
            "OpenAI-Beta": "responses=experimental",
            "originator": "codex_cli_rs",
            "chatgpt-account-id": account_id,
            "content-type": "application/json",
        },
        json=request_body,
        timeout=timeout_s,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event_type = str(event.get("type") or "")
            if event_type == "response.output_text.delta":
                delta = str(event.get("delta") or "")
                if delta:
                    text_parts.append(delta)
                continue

            if event_type == "response.completed":
                response_payload = event.get("response")
                if isinstance(response_payload, dict):
                    response_usage = response_payload.get("usage")
                    if isinstance(response_usage, dict):
                        usage = {
                            "input": int(response_usage.get("input_tokens", 0) or 0),
                            "output": int(response_usage.get("output_tokens", 0) or 0),
                            "total": int(response_usage.get("total_tokens", 0) or 0),
                        }
                break

            if "error" in event_type:
                message = _codex_error_message(event)
                raise RuntimeError(message or "ChatGPT Codex request failed")

    text = "".join(text_parts).strip()
    if not text:
        raise RuntimeError("ChatGPT Codex response did not include text content")

    latency_ms = int((time.perf_counter() - started) * 1000)
    return CodexOAuthTextResponse(text=text, latency_ms=latency_ms, usage=usage)


def _codex_error_message(event: dict[str, Any]) -> str:
    error = event.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message
    message = event.get("message")
    if isinstance(message, str) and message.strip():
        return message
    return ""
