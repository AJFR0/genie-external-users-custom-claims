"""One portal question, traced step by step. Every Databricks call uses the signed-in user's claim token."""
from __future__ import annotations

from claims_kit.claims import CLAIM_PATTERN, validate_claim
from claims_kit.trace import Trace, redact, token_view

from .redaction import screen_safe


def run_ask(services, settings, runtime, persona, question: str, new_conversation: bool) -> dict:
    trace = Trace()
    claim = persona.claim
    ex = runtime.example
    maybe = redact if settings.redact_ids else (lambda v: v)
    answer, error = None, None
    try:
        with trace.step("Session → portal user id") as s:
            s.detail = {"source": "server-side session (sign-in is simulated in this demo)", "portal_user_id": claim,
                        "persona": f"{persona.name} · {persona.label}"}
        with trace.step("Claim format check") as s:
            validate_claim(claim)
            s.detail = {"rule": CLAIM_PATTERN.pattern, "result": "valid",
                        "why": "SQL trims spaces and keeps case, so only canonical ids may be minted"}
        with trace.step("Token for the portal service principal, stamped with the claim") as s:
            token, hit = runtime.provider.token_for(claim)
            s.detail = {"cache": "hit" if hit else "minted",
                        "request": f"POST /oidc/v1/token grant_type=client_credentials custom_claim={claim}",
                        "decoded_payload": token_view(token.access_token, redact_ids=settings.redact_ids),
                        "note": "Databricks signs the token. The raw token never leaves this server."}
        auth = runtime.provider.auth_for(claim)
        with trace.step("Genie conversation, bound to this user on the server") as s:
            if not runtime.genie_space_id:
                raise RuntimeError("No Genie Agent is configured for this example")
            prior = None if new_conversation else services.conversations.get(ex.name, claim)
            result = services.make_genie(runtime.genie_space_id, auth).ask(question, prior)
            services.conversations.set(ex.name, claim, result.conversation_id)
            s.detail = {"conversation": "continued" if prior else "new", "conversation_id": maybe(result.conversation_id),
                        "message_id": maybe(result.message_id),
                        "status_timeline": [f"{t:>5.1f}s  {st}" for t, st in result.timeline]}
            if not result.completed:
                s.status = "warn"
                s.detail["note"] = result.error or f"Genie finished with status {result.status}"
        with trace.step("SQL written by Genie") as s:
            s.detail = {"sql": [q.sql for q in result.queries] or ["(no SQL for this answer)"],
                        "note": "Genie writes the same SQL for every user who asks this question. It never names the user."}
        with trace.step("Why these rows: entitlements resolved from the claim") as s:
            access = services.make_runner(auth).execute(f"SELECT * FROM {ex.fq(services.catalog, 'portal.my_access')}")
            s.detail = {"route": [f"token custom.claim = {claim}",
                                  "governance.my_effective_grants keeps grants for this claim, this service principal and "
                                  "today's date, joined to role_policies",
                                  "every portal view joins to it"],
                        "your_grants": {"columns": access.columns, "rows": access.rows}}
            if not access.rows:
                s.status = "warn"
                s.detail["note"] = "No active grants: every portal view returns no rows (fail closed)."
        if settings.enforcement == "layered":
            with trace.step("Row policies under the views") as s:
                s.detail = {"enforcement": "layered",
                            "route": ["each base table holding user data carries an ABAC row policy for this application's "
                                      "group, and masked columns a column-mask policy",
                                      "the policies admit only what this user's role may see, before any condition in "
                                      "Genie's SQL runs, so errors can't reveal other users' values",
                                      "the views still apply their own claim check, so one mistake never opens the data"]}
        else:
            with trace.step("Views only: no row policies under the views") as s:
                s.status = "warn"
                s.detail = {"enforcement": "views",
                            "note": "The claim-keyed views are the only filter. Use this mode only when your application "
                                    "controls every query; free-form questions could probe other rows through errors."}
        with trace.step("Rows returned") as s:
            s.detail = {"results": [{"columns": q.columns, "rows": q.rows[:20], "row_count": len(q.rows),
                                     "statement_id": maybe(q.statement_id)} for q in result.queries]}
        answer = {"status": result.status, "text": result.text, "error": result.error,
                  "queries": [{"sql": q.sql, "columns": q.columns, "rows": q.rows[:50]} for q in result.queries]}
        with trace.step("Audit record written") as s:
            record = services.audit.write("ask", example=ex.name, portal_user_id=claim, conversation_id=result.conversation_id,
                                          message_id=result.message_id, statement_ids=result.statement_ids,
                                          status=result.status, question=question)
            shown = {k: (maybe(v) if k in ("conversation_id", "message_id") else v) for k, v in record.items()}
            shown["statement_ids"] = [maybe(sid) for sid in record["statement_ids"]]
            s.detail = {"record": shown,
                        "note": "Query history shows the service principal. Join this record to it on statement_id."}
    except Exception as exc:
        error = str(exc)[:400]
        services.audit.write("ask_error", example=ex.name, portal_user_id=claim, error=error)
    out = {"answer": answer, "error": error, "trace": trace.to_list()}
    # Screen-sharing mode hides hosts, ids and the catalog name everywhere, including error messages.
    return screen_safe(out, settings, services.catalog, runtime.provider.client_id) if settings.redact_ids else out
