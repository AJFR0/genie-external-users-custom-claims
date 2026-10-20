"""Create the claim-keyed views in either deploy mode, plus public views and runtime grants.

Mode "null":   the workspace returns NULL without a claim, so the admin creates the views directly.
Mode "throws": current_oauth_custom_identity_claim() raises at analysis time without a claim, so a session that
               carries a claim must create the views. Only a service principal token can carry one, so the portal
               service principal gets temporary rights, creates the views, the admin takes ownership, and the
               temporary rights are revoked. The service principal ends with SELECT on portal views only.
"""
from __future__ import annotations

from typing import Callable

from .config import Example
from .sql import split_sql

DEPLOY_CLAIM = "deploy-session"
AdminSql = Callable[[str], object]


class DeployError(RuntimeError):
    """Several steps failed; every cleanup step was still attempted."""

    def __init__(self, errors: list[Exception]):
        super().__init__(f"{len(errors)} deploy steps failed: " + "; ".join(str(e)[:160] for e in errors))
        self.errors = errors


def _names(ex: Example, catalog: str) -> tuple[str, str, str, str]:
    c = f"`{catalog}`"
    return c, f"{c}.`{ex.schemas['base']}`", f"{c}.`{ex.schemas['governance']}`", f"{c}.`{ex.schemas['portal']}`"


def temporary_grants(ex: Example, catalog: str, portal_sp: str) -> list[str]:
    c, base, gov, portal = _names(ex, catalog)
    sp = f"`{portal_sp}`"
    return [
        f"GRANT USE CATALOG ON CATALOG {c} TO {sp}",
        f"GRANT USE SCHEMA, SELECT ON SCHEMA {base} TO {sp}",
        f"GRANT USE SCHEMA, SELECT, CREATE TABLE, CREATE FUNCTION ON SCHEMA {gov} TO {sp}",
        f"GRANT USE SCHEMA, CREATE TABLE ON SCHEMA {portal} TO {sp}",
    ]


def revoke_temporary_grants(ex: Example, catalog: str, portal_sp: str) -> list[str]:
    """Revoke everything temporary_grants gave. At runtime the service principal reads through its application's group."""
    c, base, gov, portal = _names(ex, catalog)
    sp = f"`{portal_sp}`"
    return [
        f"REVOKE USE SCHEMA, SELECT ON SCHEMA {base} FROM {sp}",
        f"REVOKE USE SCHEMA, SELECT, CREATE TABLE, CREATE FUNCTION ON SCHEMA {gov} FROM {sp}",
        f"REVOKE USE SCHEMA, CREATE TABLE ON SCHEMA {portal} FROM {sp}",
        f"REVOKE USE CATALOG ON CATALOG {c} FROM {sp}",
    ]


def _missing(exc: Exception) -> bool:
    text = str(exc).upper()
    return "TABLE_OR_VIEW_NOT_FOUND" in text or "DOES NOT EXIST" in text


def deploy_claim_views(ex: Example, *, catalog: str, portal_sp: str, view_owner: str, mode: str,
                       admin_sql: AdminSql, sp_runner=None) -> list[str]:
    """Create every claim-keyed view and return a log of what ran as whom."""
    if mode not in ("null", "throws"):
        raise ValueError(f"unknown deploy mode {mode!r}")
    if mode == "throws" and sp_runner is None:
        raise ValueError("throw mode needs a claim-carrying sp_runner")
    values = ex.template_values(catalog, portal_sp, view_owner)
    statements = split_sql(ex.read_sql("policy_views", values)) + split_sql(ex.read_sql("portal_views", values))
    log: list[str] = []

    def admin(stmt: str) -> None:
        log.append(f"admin: {stmt}")
        admin_sql(stmt)

    for view in reversed(ex.claim_views):
        admin(f"DROP VIEW IF EXISTS {ex.fq(catalog, view)}")
    if mode == "null":
        for stmt in statements:
            admin(stmt)
        for view in ex.claim_views:
            admin(f"ALTER VIEW {ex.fq(catalog, view)} OWNER TO `{view_owner}`")
        return log

    owned = [("VIEW", ex.fq(catalog, view)) for view in ex.claim_views]
    log += _claim_session(ex, catalog=catalog, portal_sp=portal_sp, view_owner=view_owner, admin_sql=admin_sql,
                          sp_runner=sp_runner, statements=statements, owned=owned)
    return log


def _claim_session(ex: Example, *, catalog: str, portal_sp: str, view_owner: str, admin_sql: AdminSql, sp_runner,
                   statements: list[str], owned: list[tuple[str, str]]) -> list[str]:
    """Throw mode: the portal service principal runs `statements` in a claim session with temporary rights, then the
    admin takes ownership of every object in `owned` and revokes the rights.

    Every cleanup step runs even when an earlier step failed, so the portal service principal never keeps temporary
    rights or owns an object. Errors are collected and raised together at the end.
    """
    log: list[str] = []

    def admin(stmt: str) -> None:
        log.append(f"admin: {stmt}")
        admin_sql(stmt)

    errors: list[Exception] = []
    try:
        for grant in temporary_grants(ex, catalog, portal_sp):
            admin(grant)
        for stmt in statements:
            log.append(f"portal service principal (claim session): {stmt}")
            sp_runner.execute(stmt)
    except Exception as exc:
        errors.append(exc)
    for kind, fq in owned:
        try:
            admin(f"ALTER {kind} {fq} OWNER TO `{view_owner}`")
        except Exception as exc:
            if _missing(exc):
                log.append(f"skipped ownership (not created): {fq}")
            else:
                errors.append(exc)
    for revoke in revoke_temporary_grants(ex, catalog, portal_sp):
        try:
            admin(revoke)
        except Exception as exc:
            errors.append(exc)
    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise DeployError(errors) from errors[0]
    return log


def deploy_policy_functions(ex: Example, *, catalog: str, portal_sp: str, view_owner: str, mode: str,
                            admin_sql: AdminSql, sp_runner=None) -> list[str]:
    """Create the row-filter functions. They read the claim, so in throw mode a claim session creates them."""
    if mode not in ("null", "throws"):
        raise ValueError(f"unknown deploy mode {mode!r}")
    values = ex.template_values(catalog, portal_sp, view_owner)
    statements = split_sql(ex.read_sql("policy_functions", values))
    owned = [("FUNCTION", ex.fq(catalog, f"governance.{f}")) for f in ex.claim_functions]
    if mode == "null":
        log = []
        for stmt in statements + [f"ALTER FUNCTION {fq} OWNER TO `{view_owner}`" for _, fq in owned]:
            log.append(f"admin: {stmt}")
            admin_sql(stmt)
        return log
    if sp_runner is None:
        raise ValueError("throw mode needs a claim-carrying sp_runner")
    return _claim_session(ex, catalog=catalog, portal_sp=portal_sp, view_owner=view_owner, admin_sql=admin_sql,
                          sp_runner=sp_runner, statements=statements, owned=owned)


def apply_row_policies(ex: Example, *, catalog: str, tags, group: str, admin_sql: AdminSql) -> list[str]:
    """Tag every protected table and policy column, then create the row-filter policies and default-deny."""
    from .policies import policy_statements, tag_statements
    log = []
    for stmt in tag_statements(ex, catalog, tags) + policy_statements(ex, catalog, tags, group):
        log.append(f"admin: {' '.join(stmt.split())}")
        admin_sql(stmt)
    return log


def remove_row_policies(ex: Example, *, catalog: str, admin_sql: AdminSql) -> list[str]:
    """Views-only mode: drop this example's row policies if a layered deploy created them."""
    from .policies import drop_statements
    log = []
    for stmt in drop_statements(ex, catalog):
        try:
            admin_sql(stmt)
            log.append(f"admin: {stmt}")
        except Exception as exc:
            if "POLICY_NOT_FOUND" not in str(exc).upper():
                raise
            log.append(f"skipped (absent): {stmt}")
    return log


def _run_admin_file(ex: Example, key: str, *, catalog, portal_sp, view_owner, admin_sql) -> list[str]:
    log = []
    for stmt in split_sql(ex.read_sql(key, ex.template_values(catalog, portal_sp, view_owner))):
        log.append(f"admin: {stmt}")
        admin_sql(stmt)
    return log


def create_public_views(ex: Example, **kw) -> list[str]:
    return _run_admin_file(ex, "public_views", **kw)


def apply_runtime_grants(ex: Example, **kw) -> list[str]:
    return _run_admin_file(ex, "runtime_grants", **kw)
