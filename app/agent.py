"""The agentic investigation loop — synchronous.

Kept deliberately close to v1's llm.run_investigation (same shape, same Nemotron handling),
but sync end-to-end: FastAPI runs the /api/ask route in a threadpool, so there is no asyncio
here and none of v1's TaskGroup error-surfacing pain. The model orchestrates: it reads the
schema, forms and tests hypotheses with SQL, and writes the final report.
"""
import json
import os
from typing import Callable

from . import config, prompts
from .tools import TOOL_DEFINITIONS, ToolExecutor, summarize_input

# Nemotron 3 Super emits reasoning tokens that count against max_tokens BEFORE the visible
# answer — keep this generous or the final report comes back empty.
MAX_TOKENS = 8000


def make_client():
    """OpenAI SDK pointed at the Nebius Token Factory endpoint. Reads NEBIUS_API_KEY."""
    from openai import OpenAI

    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "NEBIUS_API_KEY is not set. Get a key from https://tokenfactory.nebius.com/ and "
            "set it (e.g. in a .env file) before using the live agent."
        )
    return OpenAI(base_url=config.NEBIUS_BASE_URL, api_key=api_key)


def run_investigation(
    executor: ToolExecutor,
    question: str,
    *,
    model: str = config.NEBIUS_MODEL,
    max_turns: int = 40,
    on_event: Callable[[str, str], None] | None = None,
    context: str | None = None,
) -> str:
    """Drive the loop until the model stops calling tools; return the final report text."""

    def emit(kind: str, detail: str) -> None:
        if on_event:
            on_event(kind, detail)

    client = make_client()
    messages = [
        {"role": "system", "content": prompts.system_prompt()},
        {"role": "user", "content": prompts.user_message(question, context)},
    ]

    for _ in range(max_turns):
        resp = client.chat.completions.create(
            model=model,
            max_tokens=MAX_TOKENS,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            messages=messages,
        )
        choice = resp.choices[0]
        message = choice.message

        assistant_msg = {"role": "assistant", "content": message.content}
        if message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in message.tool_calls
            ]
        messages.append(assistant_msg)

        # No tool calls → the model is done; its text is the report. (Key off tool_calls, not
        # finish_reason: a turn can carry tool_calls AND hit the length cap.)
        if not message.tool_calls:
            report = message.content or ""
            if report.strip():
                return report
            emit("status", "Composing final report…")
            return _compose_report(client, model, messages)

        truncated = choice.finish_reason == "length"
        for tc in message.tool_calls:
            name = tc.function.name
            try:
                tool_input = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError as e:
                result = f"ERROR: malformed tool arguments JSON: {e}"
            else:
                if truncated:
                    result = "ERROR: response truncated before the tool call completed; retry."
                elif name == "note":
                    emit("note", tool_input.get("thought", ""))
                    result = executor.run("note", tool_input)
                else:
                    emit("tool", f"{name}: {summarize_input(name, tool_input)}")
                    result = executor.run(name, tool_input)
            messages.append({"role": "tool", "tool_call_id": tc.id, "name": name, "content": result})

    emit("status", "Composing report (turn budget reached)…")
    return _compose_report(client, model, messages)


def _compose_report(client, model, messages) -> str:
    resp = client.chat.completions.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=messages
        + [
            {
                "role": "user",
                "content": (
                    "Stop investigating and write your final report now, using the evidence you "
                    "gathered. Do not call any tools. Lead with the Answer, then Evidence, "
                    "Clinical interpretation, and Caveats."
                ),
            }
        ],
    )
    return resp.choices[0].message.content or ""
