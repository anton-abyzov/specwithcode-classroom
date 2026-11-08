from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)

from agents import InputGuardrailTripwireTriggered, Runner, set_tracing_export_api_key  # noqa: E402

from .router import FailoverModel, KeyRing  # noqa: E402
from .slides import deck_to_pptx  # noqa: E402
from .team import Session, build_team  # noqa: E402

if os.getenv("OPENAI_API_KEY"):
    # Agent traces go to the school's OpenAI dashboard whichever provider served the turn.
    set_tracing_export_api_key(os.environ["OPENAI_API_KEY"])

ring = KeyRing()
app = FastAPI(title="BotStack")


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[Turn] = Field(default_factory=list)
    student: str = "Maya"
    grade: str = "7"
    mode: Literal["learn", "finish"] = "finish"
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
    session = Session(student=req.student, grade=req.grade, mode=req.mode)
    items: list[Any] = [{"role": t.role, "content": t.content} for t in req.history[-8:]]
    items.append({"role": "user", "content": req.message})
    try:
        result = await Runner.run(build_team(model), items, context=session, max_turns=10)
        reply, agent = str(result.final_output), result.last_agent.name
    except InputGuardrailTripwireTriggered:
        reply = (
            "I can't help with that one. If something is worrying you, please talk to a teacher, "
            "your school counselor, or a trusted adult. I'm here whenever you want to work on schoolwork."
        )
        agent = "K-12 Safety Check"
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "reply": reply,
        "agent": agent,
        "route": [e.public() for e in model.events],
        "artifacts": session.artifacts,
        "providers": ring.snapshot(exhausted),
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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/static/{name}")
def static(name: str) -> FileResponse:
    path = (STATIC / name).resolve()
    if path.parent != STATIC or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)
