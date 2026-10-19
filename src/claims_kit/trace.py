"""A request trace: numbered steps with timings and details, shown next to every portal answer."""
from __future__ import annotations

import re
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field

from .tokens import decode_jwt_unverified

TOKEN_FIELDS = ("custom", "sub", "client_id", "aud", "iss", "scope", "exp")
ID_FIELDS = ("sub", "client_id", "aud", "iss")


@dataclass
class TraceStep:
    n: int
    title: str
    status: str = "ok"
    detail: dict = field(default_factory=dict)
    ms: float = 0.0


class Trace:
    def __init__(self, clock=time.perf_counter):
        self.steps: list[TraceStep] = []
        self._clock = clock

    @contextmanager
    def step(self, title: str):
        s = TraceStep(len(self.steps) + 1, title)
        start = self._clock()
        try:
            yield s
        except Exception as exc:
            s.status = "error"
            s.detail["error"] = str(exc)[:300]
            raise
        finally:
            s.ms = round((self._clock() - start) * 1000, 1)
            self.steps.append(s)

    def to_list(self) -> list[dict]:
        return [asdict(s) for s in self.steps]


def redact(value, keep: int = 4):
    if value is None:
        return None
    text = str(value)
    return text[:keep] + "…" if len(text) > keep else "…"


def token_view(token: str, *, redact_ids: bool, now=time.time) -> dict:
    """The decoded payload fields worth showing. The raw token itself is never shown."""
    payload = decode_jwt_unverified(token)["payload"]
    out = {k: payload[k] for k in TOKEN_FIELDS if k in payload}
    if redact_ids:
        for k in ID_FIELDS:
            if k in out:
                out[k] = redact(out[k])
    if "exp" in payload:
        out["expires_in_s"] = int(payload["exp"] - now())
    return out


def replace_identifier(obj, name: str, placeholder: str):
    """Replace a whole-word identifier (for example a catalog name) in every string inside obj."""
    import re

    pattern = re.compile(rf"(?<![\w]){re.escape(name)}(?![\w])")

    def walk(v):
        if isinstance(v, str):
            return pattern.sub(placeholder, v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v

    return walk(obj)


_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
_HEX32 = re.compile(r"\b[0-9a-f]{32}\b", re.I)


def scrub(obj, secrets: dict):
    """Replace known sensitive values, then any UUID or 32-hex id, in every string inside obj."""
    if isinstance(obj, str):
        for raw, placeholder in secrets.items():
            if raw:
                obj = obj.replace(raw, placeholder)
        return _HEX32.sub("<id>", _UUID.sub("<id>", obj))
    if isinstance(obj, list):
        return [scrub(v, secrets) for v in obj]
    if isinstance(obj, dict):
        return {k: scrub(v, secrets) for k, v in obj.items()}
    return obj
