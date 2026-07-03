"""FastAPI entry point — the OpenAI-compatible shell over the engine."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.contracts import ChatCompletionRequest, ModelList
from engine import __version__

app = FastAPI(title="M.A.R.I.A. Micro-Engine", version=__version__)


def _openai_error(status_code: int, code: str, message: str) -> JSONResponse:
    """OpenAI-shaped error body, so compatible clients surface it verbatim."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "param": "model",
                "code": code,
            }
        },
    )


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {"ok": True, "version": __version__}


@app.get("/v1/models")
def list_models() -> ModelList:
    """Loaded character packs, presented as OpenAI models.

    Pack loading is not wired yet, so the list is honestly empty.
    """
    return ModelList(data=[])


@app.post("/v1/chat/completions")
def chat_completions(request: ChatCompletionRequest) -> JSONResponse:
    """Chat with a character pack (the pack name is the `model` field).

    Neutral-fallback invariant: the engine has no built-in character, so
    with no pack loaded it reports that instead of improvising a persona.
    """
    return _openai_error(
        404,
        "model_not_found",
        f"No character pack loaded; requested model {request.model!r}. "
        "Load a character pack and pass its name as 'model'.",
    )
