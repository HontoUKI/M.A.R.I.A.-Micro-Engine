"""FastAPI entry point — the OpenAI-compatible shell over the engine."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.contracts import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    MicroEngineExtension,
    ModelCard,
    ModelList,
)
from app.deps import get_service
from app.service import EmptyConversationError, EngineService, UnknownModelError
from engine import __version__
from engine.llm import LLMError

app = FastAPI(title="M.A.R.I.A. Micro-Engine", version=__version__)

ServiceDep = Annotated[EngineService, Depends(get_service)]


def _openai_error(
    status_code: int,
    code: str,
    message: str,
    err_type: str,
    *,
    param: str | None = None,
) -> JSONResponse:
    """OpenAI-shaped error body, so compatible clients surface it verbatim."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"message": message, "type": err_type, "code": code, "param": param}
        },
    )


@app.get("/healthz")
def healthz(service: ServiceDep) -> dict[str, object]:
    # axis_max lets the web shell scale its axis bars to the deployment.
    return {"ok": True, "version": __version__, "axis_max": service.axis_max}


@app.get("/v1/models")
def list_models(service: ServiceDep) -> ModelList:
    """Loaded character packs, presented as OpenAI models."""
    return ModelList(data=[ModelCard(id=name) for name in service.model_names()])


@app.post("/v1/chat/completions")
def chat_completions(
    request: ChatCompletionRequest,
    service: ServiceDep,
) -> JSONResponse:
    """Run one character turn. The pack name is the OpenAI `model` field; the
    per-end-user `user` field keys the server-side relationship state."""
    if not service.has_model(request.model):
        return _openai_error(
            404,
            "model_not_found",
            f"No character pack named {request.model!r} is loaded.",
            "invalid_request_error",
            param="model",
        )

    session_key = request.user or "default"
    try:
        result = service.complete(request.model, request.messages, session_key=session_key)
    except UnknownModelError:
        return _openai_error(
            404,
            "model_not_found",
            f"No character pack named {request.model!r} is loaded.",
            "invalid_request_error",
            param="model",
        )
    except EmptyConversationError:
        return _openai_error(
            400,
            "empty_conversation",
            "The messages list must end with a user message.",
            "invalid_request_error",
        )
    except LLMError:
        return _openai_error(
            503,
            "llm_unavailable",
            "The language model backend is unavailable.",
            "api_error",
        )

    response = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        model=request.model,
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content=result.reply)
            )
        ],
        x_micro_engine=MicroEngineExtension(
            tag=result.tag,
            sprite=result.sprite,
            axes=result.axes.as_dict(),
            stage=result.stage,
            stage_changed=result.stage_changed,
        ),
    )
    return JSONResponse(content=response.model_dump())


# The web sprite-shell (a static single-page client) is served at the root.
# Mounted last so the API routes above always take precedence.
_WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if _WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
