"""/portal: the external user's experience, with each request's route traced step by step.

Sign-in is SIMULATED: choosing a persona stands in for your identity provider. The browser sends a persona id and
the server maps it to the portal user id. The browser never sends, sees or chooses a claim or a conversation id.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from .ask_flow import run_ask


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    new_conversation: bool = False


def current_user(request: Request, services):
    runtime = services.examples.get(request.session.get("example", ""))
    if runtime is None:
        return None
    persona = runtime.persona(request.session.get("persona", ""))
    return (runtime, persona) if persona else None


def end_session(request: Request, services) -> None:
    cur = current_user(request, services)
    if cur:
        runtime, persona = cur
        cid = services.conversations.pop(runtime.example.name, persona.claim)
        if cid and runtime.genie_space_id:
            try:
                services.make_genie(runtime.genie_space_id, runtime.provider.auth_for(persona.claim)).delete_conversation(cid)
            except Exception:  # best effort; a retention job deletes leftovers
                pass
        runtime.provider.forget(persona.claim)
        services.audit.write("sign_out", example=runtime.example.name, portal_user_id=persona.claim, conversation_id=cid)
    request.session.clear()


def build_portal_router(settings, services, templates) -> APIRouter:
    router = APIRouter()

    @router.get("/portal", response_class=HTMLResponse)
    def portal_page(request: Request):
        return templates.TemplateResponse(request, "portal.html", {"page": "portal", "examples": services.examples,
                                                                   "current": current_user(request, services)})

    @router.post("/portal/sign-in")
    def sign_in(request: Request, example: str = Form(...), persona: str = Form(...)):
        runtime = services.examples.get(example)
        chosen = runtime.persona(persona) if runtime else None
        if chosen is None:
            raise HTTPException(404, "unknown persona")
        end_session(request, services)
        request.session.update({"example": example, "persona": chosen.id})
        services.audit.write("sign_in", example=example, portal_user_id=chosen.claim)
        return RedirectResponse("/portal", status_code=303)

    @router.post("/portal/sign-out")
    def sign_out(request: Request):
        end_session(request, services)
        return RedirectResponse("/portal", status_code=303)

    @router.post("/portal/api/ask")
    def ask(request: Request, body: AskRequest):
        cur = current_user(request, services)
        if cur is None:
            raise HTTPException(401, "sign in first")
        runtime, persona = cur
        return JSONResponse(run_ask(services, settings, runtime, persona, body.question, body.new_conversation))

    return router
