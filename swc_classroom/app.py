from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

from agents import (  # noqa: E402
    InputGuardrailTripwireTriggered,
    Runner,
    gen_trace_id,
    set_tracing_export_api_key,
    trace,
)
from agents.tracing import get_trace_provider  # noqa: E402

from .router import FailoverModel, KeyRing  # noqa: E402
from .slides import deck_to_pptx  # noqa: E402
from .team import Session, build_team  # noqa: E402

if os.getenv("OPENAI_API_KEY"):
    # Agent traces go to the school's OpenAI dashboard whichever provider served the turn.
    set_tracing_export_api_key(os.environ["OPENAI_API_KEY"])

ring = KeyRing()
app = FastAPI(title="SpecWithCode Classroom")


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[Turn] = Field(default_factory=list)
    student: str = "Maya"
    grade: str = "7"
    # "finish" is the old name for "teach", kept for clients with a cached page.
    mode: Literal["learn", "teach", "finish"] = "learn"
    exhausted: list[str] = Field(default_factory=list)


@app.get("/api/ring")
def get_ring(exhausted: str = "") -> dict[str, Any]:
    return {"providers": ring.snapshot(set(filter(None, exhausted.split(","))))}


@app.post("/api/ring/reset")
def reset_ring() -> dict[str, Any]:
    ring.reset()
    return {"providers": ring.snapshot()}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    exhausted = set(req.exhausted)
    model = FailoverModel(ring, exhausted=exhausted)
    session = Session(student=req.student, grade=req.grade, mode="learn" if req.mode == "learn" else "teach")
    items: list[Any] = [{"role": t.role, "content": t.content} for t in req.history[-8:]]
    items.append({"role": "user", "content": req.message})
    trace_id = gen_trace_id()
    try:
        with trace("SpecWithCode Classroom", trace_id=trace_id, group_id=req.student):
            result = await Runner.run(build_team(model), items, context=session, max_turns=12)
        reply, agent = str(result.final_output), result.last_agent.name
    except InputGuardrailTripwireTriggered:
        reply = (
            "I can't help with that one. If something is worrying you, please talk to a teacher, "
            "your school counselor, or a trusted adult. I'm here whenever you want to work on schoolwork."
        )
        agent = "K-12 Safety Check"
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        # Serverless instances can freeze after the response; send the trace first.
        get_trace_provider().force_flush()
    return {
        "trace_id": trace_id if os.getenv("OPENAI_API_KEY") else None,
        "reply": reply,
        "agent": agent,
        "route": [e.public() for e in model.events],
        "artifacts": session.artifacts,
        "providers": ring.snapshot(exhausted),
    }


@app.get("/api/verify/{provider_id}/{response_id}")
async def verify(provider_id: str, response_id: str) -> dict[str, Any]:
    """Ask the provider itself for a past response, as proof the call happened and what it cost."""
    try:
        p = ring.get(provider_id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Unknown provider") from exc
    if p.api != "responses":
        raise HTTPException(status_code=400, detail=f"{p.label} does not offer response lookup")
    try:
        r = await ring.client(p).responses.retrieve(response_id)
    except Exception as exc:  # noqa: BLE001 - reported to the user as-is
        raise HTTPException(status_code=502, detail=f"{p.label} lookup failed: {exc}") from exc
    return {
        "provider": p.label,
        "id": r.id,
        "model": r.model,
        "status": r.status,
        "created_at": r.created_at,
        "input_tokens": r.usage.input_tokens if r.usage else None,
        "output_tokens": r.usage.output_tokens if r.usage else None,
    }


class Deck(BaseModel):
    title: str
    subtitle: str = ""
    slides: list[dict[str, Any]]


@app.post("/api/pptx")
def pptx(deck: Deck) -> StreamingResponse:
    data = deck_to_pptx(deck.model_dump())
    name = "".join(c if c.isalnum() else "-" for c in deck.title).strip("-")[:60] or "deck"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{name}.pptx"'},
    )


STATIC = ROOT / "static"


def _version(name: str) -> str:
    return hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:10]


@app.get("/")
def index() -> HTMLResponse:
    # Assets carry a content hash so a browser never pairs a new page with an old script.
    html = (STATIC / "index.html").read_text()
    for name in ("app.js", "style.css"):
        html = html.replace(f"/static/{name}", f"/static/{name}?v={_version(name)}")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/static/{name}")
def static(name: str, request: Request) -> FileResponse:
    path = (STATIC / name).resolve()
    if path.parent != STATIC or not path.is_file():
        raise HTTPException(status_code=404)
    versioned = "v" in request.query_params
    cache = "public, max-age=31536000, immutable" if versioned else "no-cache"
    return FileResponse(path, headers={"Cache-Control": cache})
