from decimal import Decimal

from claims_kit.config import load_example
from claims_kit.genie import GenieAnswer, GenieQuery
from claims_kit.personas import GenieCase, load_fixtures
from claims_kit.sql import StatementError, StatementResult
from claims_kit.tokens import MintedToken, decode_jwt_unverified
from claims_kit.validate import (SuiteContext, alg_none, attack_cases, binding_case, corrupt_signature, evaluate_genie, failures,
                                 numbers_in, privilege_cases, tamper_claim, token_cases, value_present, visibility_cases)
from conftest import FakeResponse, make_jwt

EX = load_example("northwind")
FX = load_fixtures(EX)


class Provider:
    def __init__(self, client_id="app"):
        self.client_id = client_id

    def auth_for(self, claim):
        return lambda: {"X-Claim": claim, "X-SP": self.client_id}

    def token_for(self, claim):
        return MintedToken(make_jwt({"custom": {"claim": claim}}), 9e9, claim), False

    def mint_raw(self, claim):
        return MintedToken(f"raw:{claim}", 9e9, claim)


class Admin:
    def __init__(self):
        self.statements = []

    def execute(self, sql, parameters=None):
        self.statements.append(sql)
        if sql.startswith("SHOW GRANTS"):
            return StatementResult("g", ["principal", "privilege"], [["app2", "USE CATALOG"]])
        raise StatementError("[OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED] no claim")


class Runner:
    def __init__(self, headers, handler):
        self.headers, self.handler = headers, handler

    def execute(self, sql, parameters=None):
        return self.handler(self.headers, sql)


def ctx_with(handler, **kw):
    return SuiteContext(example=EX, catalog="cat", host="https://h", warehouse_id="wh", provider=Provider(), admin=Admin(),
                        make_runner=lambda auth: Runner(auth(), handler), **kw)


def oracle(headers, sql):
    claim = headers.get("X-Claim")
    view = sql.split("`northwind_portal`.`")[1].split("`")[0]
    if headers.get("X-SP") != "app":
        return StatementResult("s", ["n"], [["0"]])
    exp = FX.views[next(p.id for p in FX.personas if p.claim == claim)][view]
    return StatementResult("s", ["k"], [[i] for i in sorted(exp.ids)])


def test_visibility_cases_pass_with_correct_rows():
    results = visibility_cases(ctx_with(oracle), FX)
    assert results and all(r.passed for r in results)


def test_visibility_case_fails_on_extra_row():
    def leaky(headers, sql):
        res = oracle(headers, sql)
        res.rows.append(["P-9999"])
        return res
    results = visibility_cases(ctx_with(leaky), FX)
    assert any(r.passed is False and "unexpected" in r.observed for r in results)


def test_attack_cases_pass_on_zero_rows_or_error():
    def handler(headers, sql):
        auth = headers.get("Authorization", "")
        if auth == "Bearer raw:None":
            raise StatementError("[OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED] none")
        if auth.startswith("Bearer raw: ") or "X-Claim" in headers:
            return StatementResult("s", ["n"], [["4"]])  # the real claim, or a padded one that SQL trims
        return StatementResult("s", ["n"], [["0"]])
    results = attack_cases(ctx_with(handler), FX)
    assert not failures(results)
    assert any(r.case_id == "documented/whitespace-trim" and r.passed for r in results)


def test_privilege_case_fails_if_statement_succeeds():
    results = privilege_cases(ctx_with(lambda *_: StatementResult("s", ["n"], [["1"]])), FX)
    assert all(r.passed is False for r in results)


def test_binding_case_revokes_what_it_granted():
    admin = Admin()

    def execute(sql, parameters=None):
        admin.statements.append(sql)
        return StatementResult("g", ["p", "priv"], [["x", "USE CATALOG"]])
    admin.execute = execute
    ctx = SuiteContext(example=EX, catalog="cat", host="h", warehouse_id="wh", provider=Provider(), admin=admin,
                       other_provider=Provider("app2"), make_runner=lambda auth: Runner(auth(), oracle))
    [result] = binding_case(ctx, FX)
    grants = [s for s in admin.statements if s.startswith("GRANT")]
    revokes = [s for s in admin.statements if s.startswith("REVOKE")]
    assert result.passed is True and len(grants) == len(revokes) == 2
    assert all(" FROM `app2`" in s for s in revokes)


def test_jwt_forgeries():
    tok = make_jwt({"custom": {"claim": "pu-1001"}, "sub": "app"})
    forged = tamper_claim(tok, "pu-1002")
    assert decode_jwt_unverified(forged)["payload"]["custom"]["claim"] == "pu-1002" and forged.split(".")[2] == tok.split(".")[2]
    assert decode_jwt_unverified(alg_none(tok))["header"]["alg"] == "none" and alg_none(tok).endswith(".")
    assert corrupt_signature(tok) != tok


def test_token_cases(fake_http):
    good = Provider().token_for("pu-1001")[0].access_token
    fake_http.route("GET", "/api/2.0/sql/warehouses/wh",
                    lambda kw: FakeResponse(200 if kw["headers"]["Authorization"] == f"Bearer {good}" else 401, {}))
    ctx = SuiteContext(example=EX, catalog="cat", host="https://h", warehouse_id="wh", provider=Provider(), admin=Admin(), http=fake_http)
    assert [r.passed for r in token_cases(ctx, FX)] == [True, True, True, True]


def test_numbers_and_value_present():
    nums = dict(numbers_in("Total $1,234.56, about 4.8M, 12K members, 7 funds"))
    assert nums[Decimal("1234.56")] == Decimal("0.005") and nums[Decimal("4800000")] == Decimal("50000")
    assert value_present(Decimal("4812345.12"), ["about $4.8M"], [])
    assert not value_present(Decimal("4912345"), ["about $4.8M"], [])
    assert value_present(Decimal("48213.47"), [], [["48213.47"]])
    assert value_present(Decimal("48213.47"), ["$48,213"], [])


def _answer(status="COMPLETED", text=(), rows=()):
    return GenieAnswer("c", "m", status, list(text), [GenieQuery("SELECT 1", None, "st", ["x"], [list(r) for r in rows])])


def test_evaluate_genie_outcomes():
    values = {"a": Decimal("1000.00"), "b": Decimal("5000.00")}
    case = GenieCase("q", ("a",), ("b",))
    assert evaluate_genie("g", "p", case, _answer(text=["$1,000.00"]), values).passed is True
    assert evaluate_genie("g", "p", case, _answer(text=["$1,000.00 and $5,000.00"]), values).passed is False
    assert evaluate_genie("g", "p", case, _answer(text=["nothing"]), values).passed is None


def test_evaluate_genie_inconclusive_when_not_completed():
    assert evaluate_genie("g", "p", GenieCase("q", ("a",)), _answer(status="FAILED"), {"a": Decimal(1)}).passed is None


def _attack_handler(error_for_injection=None):
    def handler(headers, sql):
        auth = headers.get("Authorization", "")
        if auth == "Bearer raw:None":
            raise StatementError("[OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED] none")
        if "OR '1'='1" in auth and error_for_injection:
            raise error_for_injection
        if auth.startswith("Bearer raw: ") or "X-Claim" in headers:
            return StatementResult("s", ["n"], [["4"]])
        return StatementResult("s", ["n"], [["0"]])
    return handler


def test_attack_transient_or_unexpected_error_is_inconclusive():
    for err in (StatementError("[TEMPORARILY_UNAVAILABLE] busy", error_code="TEMPORARILY_UNAVAILABLE"),
                StatementError("[DIVIDE_BY_ZERO] oops")):
        results = attack_cases(ctx_with(_attack_handler(err)), FX)
        case = next(r for r in results if r.case_id == "attack/sql-injection")
        assert case.passed is None and "inconclusive" in case.observed


def test_attack_control_character_rejection_passes_with_reason():
    err = StatementError("Query could not be scheduled: Header {X} contains characters whose code point is in [0,31] or equals 127",
                         error_code="BAD_REQUEST")
    results = attack_cases(ctx_with(_attack_handler(err)), FX)
    case = next(r for r in results if r.case_id == "attack/sql-injection")
    assert case.passed is True and "code point" in case.observed


def test_attack_token_endpoint_outcomes():
    from claims_kit.tokens import TokenError

    class P(Provider):
        def __init__(self, status):
            super().__init__()
            self.status = status

        def mint_raw(self, claim):
            if claim == "%":
                raise TokenError(self.status, "x")
            return super().mint_raw(claim)

    for status, expected in ((400, True), (503, None)):
        ctx = SuiteContext(example=EX, catalog="cat", host="h", warehouse_id="wh", provider=P(status), admin=Admin(),
                           make_runner=lambda auth: Runner(auth(), _attack_handler()))
        case = next(r for r in attack_cases(ctx, FX) if r.case_id == "attack/wildcard")
        assert case.passed is expected


def test_privilege_hidden_error_is_inconclusive_and_reason_is_recorded():
    def handler(headers, sql):
        if "account_balances" in sql:
            raise StatementError("[TABLE_OR_VIEW_NOT_FOUND] cannot be found")
        raise StatementError("[INSUFFICIENT_PERMISSIONS] User does not have USE SCHEMA on Schema", error_code="BAD_REQUEST")
    results = {r.case_id: r for r in privilege_cases(ctx_with(handler), FX)}
    assert results["privilege/read-base-table"].passed is None
    assert results["privilege/read-entitlements"].passed is True
    assert "does not have USE SCHEMA" in results["privilege/read-entitlements"].observed


def test_duplicate_rows_are_detected():
    from claims_kit.validate import duplicate_cases

    def handler(headers, sql):
        return StatementResult("s", ["n", "d"], [["5", "4" if "plan_roster" in sql else "5"]])
    results = duplicate_cases(ctx_with(handler), FX)
    assert any(r.passed is False and "plan_roster" in r.case_id for r in results)
    assert all(r.passed for r in results if "plan_roster" not in r.case_id)


def test_constraint_cases_pass_when_rejected_and_fail_and_clean_up_when_accepted():
    from claims_kit.validate import constraint_cases

    class RejectingAdmin(Admin):
        def execute(self, sql, parameters=None):
            self.statements.append(sql)
            raise StatementError("[DELTA_VIOLATE_CONSTRAINT_WITH_VALUES] CHECK constraint claim_format violated")

    class AcceptingAdmin(Admin):
        def execute(self, sql, parameters=None):
            self.statements.append(sql)
            return StatementResult("s", ["num_affected_rows"], [["1"]])

    ok = SuiteContext(example=EX, catalog="cat", host="h", warehouse_id="wh", provider=Provider(), admin=RejectingAdmin())
    assert all(r.passed is True for r in constraint_cases(ok, FX)) and len(constraint_cases(ok, FX)) == 3
    bad_admin = AcceptingAdmin()
    bad = SuiteContext(example=EX, catalog="cat", host="h", warehouse_id="wh", provider=Provider(), admin=bad_admin)
    assert all(r.passed is False for r in constraint_cases(bad, FX))
    assert sum(s.startswith("DELETE FROM") for s in bad_admin.statements) == 3
