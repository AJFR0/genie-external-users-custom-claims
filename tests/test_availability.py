from claims_kit.availability import PROBE_CLAIM, classify_no_claim, function_available, run_availability
from claims_kit.sql import StatementError, StatementResult
from claims_kit.tokens import MintedToken, TokenError


def _raises(msg):
    def f(_):
        raise RuntimeError(msg)
    return f


def test_classify_no_claim():
    assert classify_no_claim(lambda q: None) == "null"
    assert classify_no_claim(_raises("[OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED] No custom")) == "throws"
    assert classify_no_claim(_raises("[UNRESOLVED_ROUTINE] Cannot resolve routine")) == "unavailable"
    assert classify_no_claim(lambda q: "x") == "unknown"


def test_function_available():
    assert function_available(lambda q: [["Function: current_oauth_custom_identity_claim"]]) is True
    assert function_available(_raises("[UNRESOLVED_ROUTINE] nope")) is False


class Runner:
    def __init__(self, row=None, exc=None):
        self.row, self.exc = row, exc

    def execute(self, sql):
        if self.exc:
            raise self.exc
        return StatementResult("s", ["claim", "caller"], [self.row])


def test_run_availability_ready_in_throw_mode():
    report = run_availability(
        admin_scalar=_raises("[OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED]"),
        admin_any=lambda q: [["desc"]],
        mint=lambda claim: MintedToken("t", 1.0, claim),
        sp_runner_for=lambda claim: Runner([PROBE_CLAIM, "app-id"]),
    )
    assert report.ready and report.deploy_mode == "throws" and report.caller == "app-id"
    assert report.lines()[-1].startswith("READY")


def test_run_availability_not_enabled():
    def mint(claim):
        raise TokenError(403, "custom_claim is not enabled for account")
    report = run_availability(admin_scalar=lambda q: None, admin_any=lambda q: [], mint=mint, sp_runner_for=lambda c: Runner())
    assert report.mint_status == "not_enabled" and not report.ready and report.deploy_mode == "null"


def test_run_availability_roundtrip_failure_is_not_ready():
    report = run_availability(admin_scalar=lambda q: None, admin_any=lambda q: [], mint=lambda c: MintedToken("t", 1, c),
                              sp_runner_for=lambda c: Runner(exc=StatementError("[INSUFFICIENT_PERMISSIONS] warehouse")))
    assert not report.ready and "round trip failed" in report.mint_detail
