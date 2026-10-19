"""/admin: the operator's entitlement console.

Uses the operator's own Databricks identity (ADMIN_PROFILE), never a portal service principal: the portal can
only read views, and only named staff can change who sees what. Changes apply on the user's next question.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from claims_kit.claims import InvalidClaim, validate_claim
from claims_kit.sql import StatementError

from .redaction import screen_safe

KEY_WHERE = "portal_user_id = :uid AND role = :role AND scope_type = :stype AND scope_id = :sid"


class GrantKey(BaseModel):
    model_config = ConfigDict(extra="forbid")
    portal_user_id: str
    role: str
    scope_type: str
    scope_id: str


class GrantIn(GrantKey):
    valid_from: date | None = None
    valid_to: date | None = None


class PolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    value: bool | int


def _key(k: GrantKey) -> dict:
    return {"uid": k.portal_user_id, "role": k.role, "stype": k.scope_type, "sid": k.scope_id}


def _affected(result) -> int:
    try:
        return int(result.rows[0][0])
    except (IndexError, TypeError, ValueError):
        return 0


def build_admin_router(settings, services, templates) -> APIRouter:
    router = APIRouter(prefix="/admin")

    def runtime(example: str):
        rt = services.examples.get(example)
        if rt is None:
            raise HTTPException(404, f"unknown example {example!r}")
        if services.admin_runner is None:
            raise HTTPException(503, "Set ADMIN_PROFILE in .env to a Databricks CLI profile to use the admin console")
        return rt

    def table(rt, name: str) -> str:
        return rt.example.fq(services.catalog, f"governance.{name}")

    def run(sql: str, params: dict | None = None):
        try:
            return services.admin_runner.execute(sql, params)
        except StatementError as e:
            detail = e.message[:400]
            raise HTTPException(400, screen_safe(detail, settings, services.catalog) if settings.redact_ids else detail) from e

    @router.get("", response_class=HTMLResponse)
    def admin_page(request: Request):
        meta = {n: {"grant_roles": list(rt.example.grant_roles), "scope_types": list(rt.example.scope_types),
                    "role_policy_fields": rt.example.role_policy_fields} for n, rt in services.examples.items()}
        return templates.TemplateResponse(request, "admin.html", {"page": "admin", "examples": services.examples,
                                                                  "examples_json": json.dumps(meta),
                                                                  "admin_ready": services.admin_runner is not None})

    @router.get("/api/{example}/grants")
    def list_grants(example: str):
        rt = runtime(example)
        res = run(f"SELECT portal_user_id, role, scope_type, scope_id, CAST(valid_from AS STRING) AS valid_from, "
                  f"CAST(valid_to AS STRING) AS valid_to, granted_by, "
                  f"(current_date() >= valid_from AND (valid_to IS NULL OR current_date() <= valid_to)) AS active "
                  f"FROM {table(rt, 'portal_user_grants')} ORDER BY portal_user_id, role, scope_id")
        return {"columns": res.columns, "rows": res.rows}

    @router.post("/api/{example}/grants")
    def add_grant(example: str, grant: GrantIn):
        rt = runtime(example)
        try:
            validate_claim(grant.portal_user_id)
        except InvalidClaim as e:
            raise HTTPException(400, str(e)) from e
        if grant.role not in rt.example.grant_roles or grant.scope_type not in rt.example.scope_types:
            raise HTTPException(400, f"role must be one of {list(rt.example.grant_roles)}; "
                                     f"scope_type one of {list(rt.example.scope_types)}")
        run(f"INSERT INTO {table(rt, 'portal_user_grants')} "
            f"(portal_user_id, role, scope_type, scope_id, valid_from, valid_to, granted_by, granted_at) "
            f"VALUES (:uid, :role, :stype, :sid, coalesce(CAST(:vfrom AS DATE), current_date()), CAST(:vto AS DATE), "
            f"'admin console', current_timestamp())",
            {**_key(grant), "vfrom": grant.valid_from, "vto": grant.valid_to})
        services.audit.write("grant_added", example=example, portal_user_id=grant.portal_user_id,
                             detail=f"{grant.role} on {grant.scope_type} {grant.scope_id}")
        return {"ok": True}

    @router.post("/api/{example}/grants/expire")
    def expire_grant(example: str, key: GrantKey):
        rt = runtime(example)
        res = run(f"UPDATE {table(rt, 'portal_user_grants')} SET valid_to = date_sub(current_date(), 1) "
                  f"WHERE {KEY_WHERE} AND valid_from < current_date() AND (valid_to IS NULL OR valid_to >= current_date())",
                  _key(key))
        if not _affected(res):
            raise HTTPException(409, "No active grant that started before today matches. Delete it instead.")
        services.audit.write("grant_expired", example=example, portal_user_id=key.portal_user_id,
                             detail=f"{key.role} on {key.scope_id}")
        return {"ok": True}

    @router.delete("/api/{example}/grants")
    def delete_grant(example: str, key: GrantKey = Body(...)):
        rt = runtime(example)
        if not _affected(run(f"DELETE FROM {table(rt, 'portal_user_grants')} WHERE {KEY_WHERE}", _key(key))):
            raise HTTPException(404, "no matching grant")
        services.audit.write("grant_deleted", example=example, portal_user_id=key.portal_user_id,
                             detail=f"{key.role} on {key.scope_id}")
        return {"ok": True}

    @router.get("/api/{example}/role-policies")
    def list_policies(example: str):
        rt = runtime(example)
        res = run(f"SELECT * FROM {table(rt, 'role_policies')} ORDER BY role")
        return {"columns": res.columns, "rows": res.rows}

    @router.put("/api/{example}/role-policies/{role}")
    def update_policy(example: str, role: str, patch: PolicyPatch):
        rt = runtime(example)
        kind = rt.example.role_policy_fields.get(patch.field)
        if kind is None:
            raise HTTPException(400, f"field must be one of {sorted(rt.example.role_policy_fields)}")
        if kind == "boolean" and not isinstance(patch.value, bool):
            raise HTTPException(400, f"{patch.field} must be true or false")
        if kind == "int" and (isinstance(patch.value, bool) or patch.value < 0):
            raise HTTPException(400, f"{patch.field} must be a non-negative integer")
        res = run(f"UPDATE {table(rt, 'role_policies')} SET `{patch.field}` = :value WHERE role = :role",
                  {"value": patch.value, "role": role})
        if not _affected(res):
            raise HTTPException(404, f"unknown role {role!r}")
        services.audit.write("role_policy_changed", example=example, detail=f"{role}.{patch.field} = {patch.value}")
        return {"ok": True}

    @router.get("/api/audit")
    def audit_tail(limit: int = 50):
        return {"records": services.audit.tail(min(limit, 200))}

    return router
