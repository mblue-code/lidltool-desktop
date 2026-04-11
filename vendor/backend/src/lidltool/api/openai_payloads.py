from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Literal, TypeAlias, cast

if TYPE_CHECKING:
    from openai.types.chat import (
        ChatCompletionFunctionToolParam,
        ChatCompletionMessageParam,
        ChatCompletionStreamOptionsParam,
    )
else:
    ChatCompletionMessageParam: TypeAlias = dict[str, object]
    ChatCompletionFunctionToolParam: TypeAlias = dict[str, object]
    ChatCompletionStreamOptionsParam: TypeAlias = dict[str, bool]


OpenAITextRole = Literal["assistant", "system", "user"]


def simple_text_message(
    *,
    role: OpenAITextRole,
    content: str,
) -> ChatCompletionMessageParam:
    return cast(ChatCompletionMessageParam, {"role": role, "content": content})


def normalize_message_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                chunks.append(text)
        return "\n".join(chunks).strip()
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
    return ""


def to_openai_messages(
    *,
    system_prompt: str | None,
    messages: Sequence[Mapping[str, object]],
) -> list[ChatCompletionMessageParam]:
    converted: list[ChatCompletionMessageParam] = []
    if isinstance(system_prompt, str) and system_prompt.strip():
        converted.append(simple_text_message(role="system", content=system_prompt.strip()))

    for message in messages:
        raw_role = message.get("role")
        role = raw_role.strip().lower() if isinstance(raw_role, str) else "user"
        if role == "toolresult":
            role = "tool"
        if role not in {"system", "user", "assistant", "tool"}:
            role = "user"
        raw_content = message.get("content")
        if role == "assistant" and isinstance(raw_content, list):
            text_chunks: list[str] = []
            tool_calls: list[dict[str, object]] = []
            for item in raw_content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == "text" and isinstance(item.get("text"), str):
                    text_chunks.append(str(item.get("text")))
                    continue
                if item_type != "toolCall":
                    continue
                raw_name = item.get("name")
                name = raw_name.strip() if isinstance(raw_name, str) else ""
                if not name:
                    continue
                raw_id = item.get("id")
                tool_call_id = raw_id if isinstance(raw_id, str) and raw_id else f"toolcall_{len(tool_calls)}"
                arguments = item.get("arguments")
                normalized_arguments = arguments if isinstance(arguments, dict) else {}
                tool_calls.append(
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(
                                normalized_arguments,
                                separators=(",", ":"),
                            ),
                        },
                    }
                )
            if tool_calls:
                assistant_message: dict[str, object] = {
                    "role": "assistant",
                    "tool_calls": tool_calls,
                }
                text_content = "\n".join(text_chunks).strip()
                if text_content:
                    assistant_message["content"] = text_content
                converted.append(cast(ChatCompletionMessageParam, assistant_message))
                continue

        content = normalize_message_content(raw_content)
        if not content and role != "tool":
            continue
        if role == "tool":
            raw_tool_call_id = message.get("tool_call_id") or message.get("toolCallId")
            if not isinstance(raw_tool_call_id, str) or not raw_tool_call_id:
                continue
            tool_call_id = raw_tool_call_id
            converted.append(
                cast(
                    ChatCompletionMessageParam,
                    {
                        "role": "tool",
                        "content": content,
                        "tool_call_id": tool_call_id,
                    },
                )
            )
            continue
        converted.append(
            simple_text_message(
                role=cast(OpenAITextRole, role),
                content=content,
            )
        )
    return converted


def to_openai_tools(tools: Sequence[Mapping[str, object]]) -> list[ChatCompletionFunctionToolParam]:
    converted: list[ChatCompletionFunctionToolParam] = []
    for tool in tools:
        raw_name = tool.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if not name:
            continue
        raw_description = tool.get("description")
        description = raw_description.strip() if isinstance(raw_description, str) else ""
        parameters = tool.get("parameters")
        normalized_parameters = parameters if isinstance(parameters, dict) else {
            "type": "object",
            "properties": {},
        }
        converted.append(
            cast(
                ChatCompletionFunctionToolParam,
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": normalized_parameters,
                    },
                },
            )
        )
    return converted


def stream_options_with_usage() -> ChatCompletionStreamOptionsParam:
    return cast(ChatCompletionStreamOptionsParam, {"include_usage": True})
