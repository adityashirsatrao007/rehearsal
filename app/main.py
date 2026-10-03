"""Rehearsal — an offline English conversation partner.

FastAPI app. Two LLM calls run concurrently per learner turn: the streamed
in-role partner reply and the correction card. Everything runs against a local
Ollama server; nothing leaves the machine.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import coach, llm, store
from .scenarios import SCENARIOS, get_scenario, list_scenarios

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Loading a model into VRAM is slow enough that the first message would look
    # like a hang. Warm it in the background instead; never block startup.
    asyncio.create_task(llm.warm_up(llm.DEFAULT_MODEL))
    yield


app = FastAPI(title="Rehearsal", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

store.init_db()


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------

class SessionIn(BaseModel):
    scenario: str


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    model: str | None = None


# ---------------------------------------------------------------------------
# pages + metadata
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> JSONResponse:
    """Liveness + readiness probe. 200 only once the model is actually usable."""
    warm = llm.warm_status()
    ready = llm.is_warm()
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ok" if ready else warm["state"], "model": llm.DEFAULT_MODEL, **warm},
    )


@app.get("/api/status")
async def status() -> dict:
    return await llm.status()


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    return list_scenarios()


@app.get("/api/progress")
def progress() -> dict:
    return store.progress_stats()


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------

@app.post("/api/sessions")
def create_session(body: SessionIn) -> dict:
    scenario = get_scenario(body.scenario)
    if scenario is None:
        raise HTTPException(404, f"Unknown scenario '{body.scenario}'")
    return store.create_session(scenario.id, scenario.title, llm.DEFAULT_MODEL)


@app.get("/api/sessions")
def list_all_sessions() -> list[dict]:
    return store.list_sessions()


@app.get("/api/sessions/{session_id}")
def read_session(session_id: int) -> dict:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")
    return {
        "session": session,
        "messages": store.get_messages(session_id),
        "corrections": store.get_corrections(session_id),
    }


@app.delete("/api/sessions/{session_id}")
def remove_session(session_id: int) -> dict:
    if not store.delete_session(session_id):
        raise HTTPException(404, "Session not found")
    return {"deleted": session_id}


# ---------------------------------------------------------------------------
# the main turn: stream the partner, correct the learner, concurrently
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/messages")
async def send_message(session_id: int, body: MessageIn) -> StreamingResponse:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    scenario = get_scenario(session["scenario"])
    if scenario is None:
        raise HTTPException(409, "Session references an unknown scenario")

    model = (body.model or llm.DEFAULT_MODEL).strip() or llm.DEFAULT_MODEL
    learner_text = body.content.strip()

    learner_message_id = store.add_message(session_id, "learner", learner_text)

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        async def run_partner() -> None:
            history = _build_history(session_id, scenario, model)
            parts: list[str] = []
            try:
                async for delta in llm.stream_chat(model, history):
                    parts.append(delta)
                    await queue.put({"type": "reply", "delta": delta})
                content = "".join(parts).strip()
                message_id = (
                    store.add_message(session_id, "partner", content) if content else None
                )
                await queue.put(
                    {"type": "reply_done", "content": content, "message_id": message_id}
                )
            except Exception as exc:  # noqa: BLE001 — surface, never crash the stream
                await queue.put({"type": "error", "stage": "reply", "detail": str(exc)})

        async def run_correction() -> None:
            try:
                raw = await llm.generate(
                    model,
                    coach.correction_system(learner_text),
                    "Give your feedback now, in the exact three-line format.",
                )
                parsed = coach.parse_correction(raw)
                correction_id = store.add_correction(
                    session_id,
                    learner_message_id,
                    parsed["corrected"],
                    parsed["why"],
                    parsed["better"],
                )
                await queue.put(
                    {
                        "type": "correction",
                        "correction_id": correction_id,
                        "learner_message_id": learner_message_id,
                        **parsed,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                await queue.put(
                    {"type": "error", "stage": "correction", "detail": str(exc)}
                )

        await asyncio.gather(run_partner(), run_correction())
        await queue.put({"type": "done"})

        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("type") == "done":
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _build_history(session_id: int, scenario, model: str) -> list[dict]:
    """Rebuild the conversation so the local model keeps its character."""
    history: list[dict] = [{"role": "system", "content": coach.partner_system(scenario)}]
    if scenario.opening:
        history.append({"role": "assistant", "content": scenario.opening})
    for msg in store.get_messages(session_id):
        if msg["role"] == "learner":
            history.append({"role": "user", "content": msg["content"]})
        else:
            history.append({"role": "assistant", "content": msg["content"]})
    return history


# ---------------------------------------------------------------------------
# end of session scorecard
# ---------------------------------------------------------------------------

@app.post("/api/sessions/{session_id}/summary")
async def summarise(session_id: int) -> dict:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(404, "Session not found")

    turns = store.learner_turns(session_id)
    if not turns:
        raise HTTPException(409, "Nothing to review yet — send a message first.")

    model = session.get("model") or llm.DEFAULT_MODEL
    try:
        raw = await llm.generate(
            model,
            coach.summary_system(session["scenario_title"], turns),
            "Give your five-line review now.",
            options=llm.SUMMARY_OPTIONS,
        )
    except llm.LLMUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    parsed = coach.parse_summary(raw)
    store.finish_session(
        session_id,
        parsed["fluency"],
        parsed["accuracy"],
        parsed["vocabulary"],
        parsed["summary"],
        parsed["next_step"],
    )
    return {"session_id": session_id, **parsed, "stats": store.progress_stats()}


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("REHEARSAL_HOST", "127.0.0.1"),
        port=int(os.environ.get("REHEARSAL_PORT", "8000")),
        reload=False,
    )
