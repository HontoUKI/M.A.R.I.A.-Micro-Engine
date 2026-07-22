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
    ChatCompletionUsage,
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
        result = service.complete(
            request.model,
            request.messages,
            session_key=session_key,
            language=request.language,
            user_gender=request.user_gender,
        )
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
        usage=ChatCompletionUsage(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        ),
        x_micro_engine=MicroEngineExtension(
            tag=result.tag,
            sprite=result.sprite,
            axes=result.axes.as_dict(),
            stage=result.stage,
            stage_changed=result.stage_changed,
        ),
    )
    return JSONResponse(content=response.model_dump())


# --------------------------------------------------------------- session history
# Per (user, character) transcript management for the web shell. Not part of the
# OpenAI-compatible surface.


def _known_model_or_404(service: EngineService, model: str) -> JSONResponse | None:
    if service.has_model(model):
        return None
    return _openai_error(
        404, "model_not_found", f"No character pack named {model!r}.",
        "invalid_request_error", param="model",
    )


@app.get("/sessions/{model}/days")
def session_days(model: str, service: ServiceDep, user: str = "default") -> JSONResponse:
    """Dates that have a saved conversation with this character."""
    if (err := _known_model_or_404(service, model)) is not None:
        return err
    return JSONResponse(content={"days": service.history_days(model, user)})


@app.get("/sessions/{model}/transcript")
def session_transcript(
    model: str, service: ServiceDep, user: str = "default", day: str | None = None
) -> JSONResponse:
    """The saved turns for a character, optionally filtered to one day."""
    if (err := _known_model_or_404(service, model)) is not None:
        return err
    return JSONResponse(content={"turns": service.history(model, user, day)})


@app.delete("/sessions/{model}/transcript")
def clear_session_transcript(
    model: str, service: ServiceDep, user: str = "default", day: str | None = None
) -> JSONResponse:
    """Clear the whole transcript, or just one day's entries."""
    if (err := _known_model_or_404(service, model)) is not None:
        return err
    return JSONResponse(content={"cleared": service.clear_history(model, user, day)})


@app.post("/sessions/{model}/reset")
def reset_session(model: str, service: ServiceDep, user: str = "default") -> JSONResponse:
    """Forget the relationship (reset the axes to the pack baseline)."""
    if (err := _known_model_or_404(service, model)) is not None:
        return err
    service.reset_relationship(model, user)
    return JSONResponse(content={"ok": True})


# The web sprite-shell (a static single-page client) is served at the root.
# Mounted last so the API routes above always take precedence.
_WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if _WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
