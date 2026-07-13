"""FastAPI app: serves the static console and the optional live-agent API.

Design: the console (GET /) is a self-contained static file that works with zero
credentials — the clone-and-run viewer. The agent (POST /api/ask) is optional and only
works when NEBIUS_API_KEY is set. The /api/ask route is defined `def` (not `async def`) so
FastAPI runs the synchronous investigation loop in a threadpool.
"""
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import agent, config, dataset
from .tools import ToolExecutor

app = FastAPI(title="ClinicalxCRAFT v2", description="KIRC cohort console — static viewer + optional LLM agent")


@app.get("/")
def index():
    return FileResponse(config.WEB_DIR / "index.html")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "cohort": config.COHORT_LABEL,
        "patients": dataset.count(),
        "model": config.NEBIUS_MODEL,
        "llm_configured": bool(os.environ.get("NEBIUS_API_KEY")),
    }


@app.get("/api/schema")
def schema():
    return {"schema": dataset.schema_doc()}


class AskRequest(BaseModel):
    question: str
    context: str | None = None


@app.post("/api/ask")
def ask(req: AskRequest):
    """Run one investigation. Returns the report, the live trace, and the SQL the agent ran.

    Blocks until the investigation finishes (Nemotron is slow to first token; a full run can
    take up to a minute). Streaming the trace over SSE is the natural next enhancement.
    """
    if not req.question.strip():
        return JSONResponse(status_code=400, content={"error": "question is required"})

    executor = ToolExecutor()
    trace: list[dict] = []

    def on_event(kind: str, detail: str) -> None:
        trace.append({"kind": kind, "detail": detail})

    try:
        report = agent.run_investigation(executor, req.question, on_event=on_event, context=req.context)
    except RuntimeError as e:  # missing key → clean, actionable message for the frontend
        return JSONResponse(status_code=503, content={"error": str(e), "needs_key": True})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"{type(e).__name__}: {e}"})

    return {"answer": report, "trace": trace, "sql": executor.sql_log}
