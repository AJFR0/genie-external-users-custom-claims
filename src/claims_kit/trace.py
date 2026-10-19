"""A request trace: numbered steps with timings and details, shown next to every portal answer."""
from __future__ import annotations

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
