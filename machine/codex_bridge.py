"""Turn a computer signed in to Codex into a machine on the Key Ring.

The bridge speaks the Chat Completions protocol the ring expects and answers each call
by running `codex exec` with the computer's own ChatGPT sign-in, so the work is billed
to that ChatGPT plan instead of API credits. Tool calls are returned as structured
output, which keeps the Agents SDK handoffs and tools working on this machine.

Run on the machine:
    SWC_MACHINE_KEY=<shared secret> python machine/codex_bridge.py
then expose port 8790 (for example with `cloudflared tunnel --url http://127.0.0.1:8790`)
and add the URL to SWC_MACHINES on the server.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException

MODEL = os.getenv("CODEX_MODEL", "gpt-6-luna")
KEY = os.getenv("SWC_MACHINE_KEY", "")
LIMIT = asyncio.Semaphore(int(os.getenv("CODEX_PARALLEL", "2")))

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["kind", "content", "tool_name", "arguments_json"],
    "properties": {
        "kind": {"type": "string", "enum": ["message", "tool_call"]},
        "content": {"type": "string"},
        "tool_name": {"type": "string"},
        "arguments_json": {"type": "string"},
    },
}

app = FastAPI(title="Codex machine bridge")


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return "" if content is None else str(content)


def build_prompt(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> str:
    lines = [
        "You are one step of a chat-completions call. Do not run commands or edit files.",
        "Read the conversation and produce the assistant's next turn.",
    ]
    if tools:
        lines.append("\nTools you may call (one per turn). arguments_json must be a JSON object string matching the parameters:")
        for t in tools:
            fn = t.get("function", t)
            lines.append(f"- {fn['name']}: {fn.get('description', '')}\n  parameters: {json.dumps(fn.get('parameters', {}))}")
        lines.append(
            "Reply kind=tool_call with tool_name and arguments_json to call a tool, or kind=message "
            "with the full reply in content. Leave unused fields as empty strings."
        )
    else:
        lines.append("Reply kind=message with the full reply in content.")
    lines.append("\nConversation:")
    for m in messages:
        role = m.get("role")
        if role == "tool":
            lines.append(f"[tool result {m.get('tool_call_id', '')}]\n{_text(m.get('content'))}")
        elif m.get("tool_calls"):
            for c in m["tool_calls"]:
                lines.append(f"[assistant called {c['function']['name']}] {c['function']['arguments']}")
        else:
            lines.append(f"[{role}]\n{_text(m.get('content'))}")
    return "\n".join(lines)


async def run_codex(prompt: str) -> tuple[dict[str, Any], dict[str, int]]:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "schema.json").write_text(json.dumps(SCHEMA))
        proc = await asyncio.create_subprocess_exec(
            "codex", "exec", "-m", MODEL, "--json", "--ephemeral", "--skip-git-repo-check",
            "-s", "read-only", "-C", str(work), "--output-schema", str(work / "schema.json"),
            "-o", str(work / "out.json"), "-",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(prompt.encode()), timeout=240)
        usage: dict[str, int] = {}
        for line in stdout.decode().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "turn.completed":
                usage = event.get("usage", {})
            if event.get("type") in ("turn.failed", "error"):
                raise HTTPException(status_code=503, detail=str(event.get("error") or event.get("message")))
        out = work / "out.json"
        if not out.exists():
            raise HTTPException(status_code=503, detail="Codex returned no answer")
        return json.loads(out.read_text()), usage


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "codex-chatgpt-plan"}]}


@app.post("/v1/chat/completions")
async def chat(body: dict[str, Any], authorization: str = Header(default="")) -> dict[str, Any]:
    if not KEY or authorization != f"Bearer {KEY}":
        raise HTTPException(status_code=401, detail="Wrong machine key")
    async with LIMIT:
        reply, usage = await run_codex(build_prompt(body.get("messages", []), body.get("tools") or []))
    message: dict[str, Any] = {"role": "assistant", "content": reply.get("content") or None}
    finish = "stop"
    if reply.get("kind") == "tool_call" and reply.get("tool_name"):
        message["content"] = None
        message["tool_calls"] = [{
            "id": f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {"name": reply["tool_name"], "arguments": reply.get("arguments_json") or "{}"},
        }]
        finish = "tool_calls"
    prompt_tokens = usage.get("input_tokens", 0)
    completion_tokens = usage.get("output_tokens", 0)
    return {
        "id": f"chatcmpl-codex-{uuid.uuid4().hex[:20]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8790")))
