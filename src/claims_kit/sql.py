"""Run SQL through the Statement Execution API as any identity, plus small SQL helpers."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

import requests

AuthFn = Callable[[], dict[str, str]]
_ERROR_CLASS = re.compile(r"\[([A-Z][A-Z0-9_.]+)\]")
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
_UNSAFE_VALUE = re.compile(r"[`'\";\\\n\r]")
_DENIED = ("PERMISSION_DENIED", "INSUFFICIENT_PERMISSIONS", "DOES NOT HAVE", "UNAUTHORIZED")
_HIDDEN = ("TABLE_OR_VIEW_NOT_FOUND", "SCHEMA_NOT_FOUND", "NO_SUCH_CATALOG", "CATALOG_NOT_FOUND")
_TRANSIENT = ("TEMPORARILY_UNAVAILABLE", "RESOURCE_EXHAUSTED")


class StatementError(RuntimeError):
    def __init__(self, message: str, *, error_code: str | None = None, statement_id: str | None = None, http_status: int | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.statement_id = statement_id
        self.http_status = http_status

    @property
    def error_class(self) -> str | None:
        m = _ERROR_CLASS.search(self.message)
        return m.group(1) if m else self.error_code

    @property
    def is_permission_error(self) -> bool:
        text = f"{self.error_code or ''} {self.message}".upper()
        return any(k in text for k in _DENIED)

    @property
    def is_transient(self) -> bool:
        """Warehouse or API hiccups worth retrying; never an authorization outcome."""
        return self.http_status in (429, 503) or (self.error_class or "") in _TRANSIENT or (self.error_code or "") in _TRANSIENT

    @property
    def is_denied_or_hidden(self) -> bool:
        """Unity Catalog either denies or hides objects the caller has no privileges on."""
        text = f"{self.error_code or ''} {self.message}".upper()
        return self.is_permission_error or any(k in text for k in _HIDDEN)


@dataclass
class StatementResult:
    statement_id: str
    columns: list[str]
    rows: list[list] = field(default_factory=list)

    def dicts(self) -> list[dict]:
        return [dict(zip(self.columns, row)) for row in self.rows]

    def scalar(self):
        return self.rows[0][0] if self.rows else None


def _param(name: str, value) -> dict:
    if value is None:
        return {"name": name, "type": "STRING"}
    if isinstance(value, bool):
        return {"name": name, "value": "true" if value else "false", "type": "BOOLEAN"}
    if isinstance(value, int):
        return {"name": name, "value": str(value), "type": "INT"}
    if isinstance(value, date):
        return {"name": name, "value": value.isoformat(), "type": "DATE"}
    return {"name": name, "value": str(value), "type": "STRING"}


def _json_or_raise(resp) -> dict:
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        raise StatementError(body.get("message") or resp.text[:500], error_code=body.get("error_code"), http_status=resp.status_code)
    return resp.json()


class StatementRunner:
    """Executes statements with whatever identity `auth` returns headers for (admin or claim token)."""

    def __init__(self, host: str, warehouse_id: str, auth: AuthFn, *, http=None, poll_s: float = 1.0, timeout_s: float = 300,
                 sleep=time.sleep, clock=time.monotonic):
        self.host = host.rstrip("/")
        self.warehouse_id = warehouse_id
        self.auth = auth
        self._http = http or requests
        self._poll_s = poll_s
        self._timeout_s = timeout_s
        self._sleep = sleep
        self._clock = clock

    def execute(self, statement: str, parameters: dict[str, object] | None = None, *, attempts: int = 3) -> StatementResult:
        """Run one statement. Transient warehouse errors are retried with a short backoff; nothing else is."""
        for attempt in range(1, attempts + 1):
            try:
                return self._execute_once(statement, parameters)
            except StatementError as exc:
                if not exc.is_transient or attempt == attempts:
                    raise
                self._sleep(2 * attempt)
        raise AssertionError("unreachable")

    def _execute_once(self, statement: str, parameters: dict[str, object] | None) -> StatementResult:
        body: dict = {"statement": statement, "warehouse_id": self.warehouse_id, "wait_timeout": "30s",
                      "on_wait_timeout": "CONTINUE", "format": "JSON_ARRAY", "disposition": "INLINE"}
        if parameters:
            body["parameters"] = [_param(k, v) for k, v in parameters.items()]
        payload = _json_or_raise(self._http.post(f"{self.host}/api/2.0/sql/statements", json=body, headers=self.auth(), timeout=60))
        deadline = self._clock() + self._timeout_s
        while payload["status"]["state"] in ("PENDING", "RUNNING"):
            if self._clock() > deadline:
                raise StatementError("statement timed out", statement_id=payload.get("statement_id"))
            self._sleep(self._poll_s)
            payload = _json_or_raise(self._http.get(f"{self.host}/api/2.0/sql/statements/{payload['statement_id']}",
                                                    headers=self.auth(), timeout=60))
        if payload["status"]["state"] != "SUCCEEDED":
            err = payload["status"].get("error") or {}
            raise StatementError(err.get("message", payload["status"]["state"]), error_code=err.get("error_code"),
                                 statement_id=payload.get("statement_id"))
        columns = [c["name"] for c in payload.get("manifest", {}).get("schema", {}).get("columns", [])]
        result = payload.get("result") or {}
        rows = list(result.get("data_array") or [])
        link = result.get("next_chunk_internal_link")
        while link:
            chunk = _json_or_raise(self._http.get(f"{self.host}{link}", headers=self.auth(), timeout=60))
            rows.extend(chunk.get("data_array") or [])
            link = chunk.get("next_chunk_internal_link")
        return StatementResult(payload["statement_id"], columns, rows)

    def execute_script(self, script: str) -> list[StatementResult]:
        return [self.execute(s) for s in split_sql(script)]


def split_sql(script: str) -> list[str]:
    """Split a script on top-level semicolons; drop comments; keep quoted text intact."""
    statements: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i, n = 0, len(script)
    while i < n:
        ch = script[i]
        nxt = script[i + 1] if i + 1 < n else ""
        if quote:
            buf.append(ch)
            if ch == "\\" and quote in "'\"" and nxt:
                buf.append(nxt)
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == "-" and nxt == "-":
            j = script.find("\n", i)
            i = n if j == -1 else j
            continue
        if ch == "/" and nxt == "*":
            j = script.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if ch in ("'", '"', "`"):
            quote = ch
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def render_template(text: str, values: dict[str, str]) -> str:
    """Replace {{name}} placeholders. Values may not contain quotes, backticks, semicolons or newlines."""
    for key, value in values.items():
        if _UNSAFE_VALUE.search(str(value)):
            raise ValueError(f"unsafe template value for {key!r}")

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            raise KeyError(f"no value for template placeholder {key!r}")
        return str(values[key])

    return _PLACEHOLDER.sub(sub, text)
