import pytest

from claims_kit.trace import Trace, redact, token_view
from conftest import make_jwt


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 0.25
        return self.t


def test_steps_are_numbered_timed_and_errors_reraised():
    trace = Trace(clock=Clock())
    with trace.step("one") as s:
        s.detail["a"] = 1
    with pytest.raises(ValueError):
        with trace.step("two"):
            raise ValueError("bad")
    steps = trace.to_list()
    assert [(s["n"], s["title"], s["status"]) for s in steps] == [(1, "one", "ok"), (2, "two", "error")]
    assert steps[0]["ms"] == 250.0 and steps[1]["detail"]["error"] == "bad"


def test_token_view_keeps_claim_and_redacts_ids():
    tok = make_jwt({"custom": {"claim": "pu-1001"}, "sub": "abcdef-1234", "client_id": "abcdef-1234", "aud": "999988887777",
                    "iss": "https://host.example/oidc", "exp": 1100})
    view = token_view(tok, redact_ids=True, now=lambda: 1000)
    assert view["custom"] == {"claim": "pu-1001"} and view["sub"] == "abcd…" and view["iss"] == "http…" and view["expires_in_s"] == 100
    assert token_view(tok, redact_ids=False, now=lambda: 1000)["aud"] == "999988887777"


def test_redact():
    assert redact(None) is None and redact("ab") == "…" and redact("abcdef") == "abcd…"
