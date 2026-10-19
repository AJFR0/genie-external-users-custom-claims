"""Minimal Genie Conversation API client. Every call runs with a caller-supplied (claim) token."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import requests

from .sql import AuthFn

TERMINAL = frozenset({"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"})
MAX_ROWS = 200


class GenieError(RuntimeError):
    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


@dataclass
class GenieQuery:
    sql: str
    description: str | None
    statement_id: str | None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)


@dataclass
class GenieAnswer:
    conversation_id: str
    message_id: str
    status: str
    text: list[str] = field(default_factory=list)
    queries: list[GenieQuery] = field(default_factory=list)
    timeline: list[tuple[float, str]] = field(default_factory=list)
    error: str | None = None

    @property
    def completed(self) -> bool:
        return self.status == "COMPLETED"

    @property
    def statement_ids(self) -> list[str]:
        return [q.statement_id for q in self.queries if q.statement_id]


class GenieClient:
    def __init__(self, host: str, space_id: str, auth: AuthFn, *, http=None, poll_initial_s=1.0, poll_max_s=5.0, timeout_s=600.0,
                 sleep=time.sleep, clock=time.monotonic):
        self.base = f"{host.rstrip('/')}/api/2.0/genie/spaces/{space_id}"
        self.auth = auth
        self._http = http or requests
        self._poll_initial = poll_initial_s
        self._poll_max = poll_max_s
        self._timeout = timeout_s
        self._sleep = sleep
        self._clock = clock

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        kwargs = {"headers": self.auth(), "timeout": 60}
        if body is not None:
            kwargs["json"] = body
        resp = getattr(self._http, method)(f"{self.base}{path}", **kwargs)
        if resp.status_code >= 400:
            raise GenieError(f"{method.upper()} {path} -> HTTP {resp.status_code}: {resp.text[:300]}", resp.status_code)
        return resp.json() if resp.text else {}

    def ask(self, question: str, conversation_id: str | None = None) -> GenieAnswer:
        start = self._clock()
        if conversation_id is None:
            r = self._call("post", "/start-conversation", {"content": question})
            conversation_id, message_id = r["conversation_id"], r["message_id"]
        else:
            r = self._call("post", f"/conversations/{conversation_id}/messages", {"content": question})
            message_id = r.get("message_id") or r["id"]
        timeline: list[tuple[float, str]] = []
        delay, last, message = self._poll_initial, None, {}
        while True:
            message = self.get_message(conversation_id, message_id)
            status = message.get("status", "UNKNOWN")
            if status != last:
                timeline.append((round(self._clock() - start, 2), status))
                last = status
            if status in TERMINAL:
                break
            if self._clock() - start > self._timeout:
                return GenieAnswer(conversation_id, message_id, "TIMEOUT", timeline=timeline, error="timed out waiting for Genie")
            self._sleep(delay)
            delay = min(delay * 1.5, self._poll_max)
        answer = GenieAnswer(conversation_id, message_id, status, timeline=timeline)
        err = message.get("error")
        if err:
            answer.error = err.get("error") if isinstance(err, dict) else str(err)
        for att in message.get("attachments") or []:
            if att.get("text"):
                answer.text.append(att["text"].get("content", ""))
            q = att.get("query")
            if q:
                gq = GenieQuery(sql=q.get("query", ""), description=q.get("description"), statement_id=q.get("statement_id"))
                if answer.completed and att.get("attachment_id"):
                    cols, rows, sid = self.query_result(conversation_id, message_id, att["attachment_id"])
                    gq.columns, gq.rows = cols, rows[:MAX_ROWS]
                    gq.statement_id = gq.statement_id or sid
                answer.queries.append(gq)
        return answer

    def get_message(self, conversation_id: str, message_id: str) -> dict:
        return self._call("get", f"/conversations/{conversation_id}/messages/{message_id}")

    def query_result(self, conversation_id: str, message_id: str, attachment_id: str) -> tuple[list[str], list[list], str | None]:
        r = self._call("get", f"/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/query-result")
        sr = r.get("statement_response") or {}
        cols = [c["name"] for c in sr.get("manifest", {}).get("schema", {}).get("columns", [])]
        rows = (sr.get("result") or {}).get("data_array") or []
        return cols, rows, sr.get("statement_id")

    def delete_conversation(self, conversation_id: str) -> None:
        self._call("delete", f"/conversations/{conversation_id}")
