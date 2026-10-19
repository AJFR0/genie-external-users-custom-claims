"""Isolation suite: proves every security layer with real tokens against a deployed example.

  visibility   each persona sees exactly the ids its grants allow, in every portal view
  role_effect  masking and other column rules that come from role_policies
  attack       no claim, forged or malformed claims, an admin session without a claim
  privilege    the portal service principal can't read base or governance objects, change entitlements or run DDL
  cross_app    another application's service principal can't read this application's views
  binding      even with a mistaken grant, a view answers only for its own application's service principal
  token        edited, unsigned and corrupted tokens are rejected
  genie        Genie answers contain the persona's numbers and none of anyone else's
  documented   platform behaviors a backend must account for; never fails the run
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

import requests

from .config import Example, load_example
from .genie import GenieAnswer, GenieClient, GenieError
from .personas import ExampleFixtures, GenieCase, load_fixtures
from .sql import StatementError, StatementRunner
from .tokens import ClaimTokenProvider, TokenError, decode_jwt_unverified

CATEGORIES = ("visibility", "role_effect", "attack", "privilege", "cross_app", "binding", "token", "genie", "documented")
ATTACK_VARIANTS = (
    ("sql-injection", "{claim}' OR '1'='1"),
    ("wildcard", "%"),
    ("prefix-wildcard", "{prefix}%"),
    ("uppercase", "{upper}"),
    ("control-character", "{claim}\t"),
)


@dataclass
class CaseResult:
    case_id: str
    category: str
    persona: str | None
    passed: bool | None
    expected: str
    observed: str
    statement_id: str | None = None


@dataclass
class SuiteContext:
    example: Example
    catalog: str
    host: str
    warehouse_id: str
    provider: ClaimTokenProvider
    admin: object
    other_provider: ClaimTokenProvider | None = None
    genie_space_id: str | None = None
    include_genie: bool = True
    http: object = requests
    make_runner: Callable | None = None
    make_genie: Callable | None = None

    def runner(self, auth):
        return self.make_runner(auth) if self.make_runner else StatementRunner(self.host, self.warehouse_id, auth, http=self.http)

    def sp_runner(self, claim, provider=None):
        return self.runner((provider or self.provider).auth_for(claim))

    def raw_runner(self, token: str):
        return self.runner(lambda: {"Authorization": f"Bearer {token}"})

    def genie(self, claim):
        auth = self.provider.auth_for(claim)
        if self.make_genie:
            return self.make_genie(self.genie_space_id, auth)
        return GenieClient(self.host, self.genie_space_id, auth, http=self.http)

    def view(self, name: str) -> str:
        return self.example.fq(self.catalog, f"portal.{name}")


def _err(e: Exception) -> str:
    if isinstance(e, StatementError):
        return f"error: {e.error_class or e.message[:120]}"
    return f"error: {str(e)[:120]}"


def _fmt(ids, limit=6) -> str:
    s = sorted(ids)
    if not s:
        return "0 ids"
    more = ", …" if len(s) > limit else ""
    return f"{len(s)} ids ({', '.join(s[:limit])}{more})"


def _target(fx: ExampleFixtures):
    for p in fx.personas:
        for view, exp in sorted(fx.views[p.id].items()):
            if exp.ids and view != "my_access":
                return p, view
    raise ValueError("no persona with visible rows")


def _count(runner, sql) -> tuple[int, str]:
    res = runner.execute(sql)
    return int(res.scalar()), res.statement_id


def visibility_cases(ctx: SuiteContext, fx: ExampleFixtures) -> list[CaseResult]:
    out = []
    for p in fx.personas:
        runner = ctx.sp_runner(p.claim)
        for view, exp in sorted(fx.views[p.id].items()):
            case_id = f"visibility/{p.id}/{view}"
            cols = ", ".join(f"CAST(`{k}` AS STRING)" for k in exp.key)
            try:
                res = runner.execute(f"SELECT DISTINCT concat_ws('|', {cols}) AS k FROM {ctx.view(view)}")
            except StatementError as e:
                out.append(CaseResult(case_id, "visibility", p.id, False, _fmt(exp.ids), _err(e), e.statement_id))
                continue
            got = frozenset(r[0] for r in res.rows)
            ok = got == exp.ids
            observed = _fmt(got) if ok else f"{_fmt(got)}; missing {_fmt(exp.ids - got)}; unexpected {_fmt(got - exp.ids)}"
            out.append(CaseResult(case_id, "visibility", p.id, ok, _fmt(exp.ids), observed, res.statement_id))
    return out


def role_effect_cases(ctx: SuiteContext, fx: ExampleFixtures) -> list[CaseResult]:
    out = []
    for p in fx.personas:
        runner = ctx.sp_runner(p.claim)
        for view, exp in sorted(fx.views[p.id].items()):
            checks = [(c, "masked: every value NULL") for c in exp.null_columns] + \
                     [(c, "visible: no NULL values") for c in exp.not_null_columns]
            for col, want in checks:
                case_id = f"role_effect/{p.id}/{view}.{col}"
                try:
                    res = runner.execute(f"SELECT count(*) AS n, count(`{col}`) AS non_null FROM {ctx.view(view)}")
                except StatementError as e:
                    out.append(CaseResult(case_id, "role_effect", p.id, False, want, _err(e), e.statement_id))
                    continue
                n, non_null = int(res.rows[0][0]), int(res.rows[0][1])
                ok = n > 0 and (non_null == 0 if want.startswith("masked") else non_null == n)
                out.append(CaseResult(case_id, "role_effect", p.id, ok, want, f"{non_null} of {n} rows non-NULL", res.statement_id))
            if exp.never_equal:
                col, forbidden = exp.never_equal
                case_id = f"role_effect/{p.id}/{view}.{col}"
                want = f"{col} never shows a raw identifier"
                try:
                    res = runner.execute(f"SELECT DISTINCT CAST(`{col}` AS STRING) FROM {ctx.view(view)}")
                except StatementError as e:
                    out.append(CaseResult(case_id, "role_effect", p.id, False, want, _err(e), e.statement_id))
                    continue
                values = {r[0] for r in res.rows}
                overlap = values & set(forbidden)
                ok = bool(values) and not overlap and None not in values
                out.append(CaseResult(case_id, "role_effect", p.id, ok, want,
                                      f"{len(values)} distinct values, {len(overlap)} raw identifiers", res.statement_id))
    return out


def attack_cases(ctx: SuiteContext, fx: ExampleFixtures) -> list[CaseResult]:
    persona, view = _target(fx)
    count_sql = f"SELECT count(*) FROM {ctx.view(view)}"
    want = "0 rows or an error"
    out = []
    variants = [("no-claim", None)] + [
        (name, template.format(claim=persona.claim, prefix=ctx.example.claim_prefix, upper=persona.claim.upper()))
        for name, template in ATTACK_VARIANTS]
    for name, claim in variants:
        case_id = f"attack/{name}"
        try:
            token = ctx.provider.mint_raw(claim)
        except TokenError as e:
            out.append(CaseResult(case_id, "attack", None, True, want, f"token request rejected (HTTP {e.status})"))
            continue
        try:
            n, sid = _count(ctx.raw_runner(token.access_token), count_sql)
            out.append(CaseResult(case_id, "attack", None, n == 0, want, f"{n} rows", sid))
        except StatementError as e:
            out.append(CaseResult(case_id, "attack", None, True, want, _err(e), e.statement_id))
    try:
        n, sid = _count(ctx.admin, count_sql)
        out.append(CaseResult("attack/admin-without-claim", "attack", None, n == 0, want, f"{n} rows", sid))
    except StatementError as e:
        out.append(CaseResult("attack/admin-without-claim", "attack", None, True, want, _err(e), e.statement_id))
    want_trim = "a claim with surrounding spaces matches the trimmed claim, so validate claims before minting"
    try:
        expected, _ = _count(ctx.sp_runner(persona.claim), count_sql)
        n, sid = _count(ctx.raw_runner(ctx.provider.mint_raw(f" {persona.claim} ").access_token), count_sql)
        out.append(CaseResult("documented/whitespace-trim", "documented", persona.id, n == expected and n > 0, want_trim,
                              f"{n} rows vs {expected}", sid))
    except (StatementError, TokenError) as e:
        out.append(CaseResult("documented/whitespace-trim", "documented", persona.id, False, want_trim, _err(e)))
    return out


def privilege_cases(ctx: SuiteContext, fx: ExampleFixtures) -> list[CaseResult]:
    ex, c = ctx.example, ctx.catalog
    runner = ctx.sp_runner(fx.personas[0].claim)
    probe_view = ex.fq(c, "portal.zz_isolation_probe")
    probes = [
        ("privilege/read-base-table", f"SELECT count(*) FROM {ex.fq(c, 'base.' + ex.base_probe_table)}"),
        ("privilege/read-entitlements", f"SELECT count(*) FROM {ex.fq(c, 'governance.portal_user_grants')}"),
        ("privilege/read-role-policies", f"SELECT count(*) FROM {ex.fq(c, 'governance.role_policies')}"),
        ("privilege/read-policy-view", f"SELECT count(*) FROM {ex.fq(c, 'governance.my_effective_grants')}"),
        ("privilege/change-entitlements", f"UPDATE {ex.fq(c, 'governance.portal_user_grants')} SET granted_by = granted_by WHERE 1 = 0"),
        ("privilege/create-view", f"CREATE VIEW {probe_view} AS SELECT 1 AS x"),
    ]
    out = []
    for case_id, sql in probes:
        try:
            res = runner.execute(sql)
            out.append(CaseResult(case_id, "privilege", None, False, "denied", "statement succeeded", res.statement_id))
            if case_id.endswith("create-view"):
                try:
                    ctx.admin.execute(f"DROP VIEW IF EXISTS {probe_view}")
                except StatementError:
                    pass
        except StatementError as e:
            out.append(CaseResult(case_id, "privilege", None, e.is_denied_or_hidden, "denied", _err(e), e.statement_id))
    return out


def _skipped(case_id, category, expected):
    return CaseResult(case_id, category, None, None, expected, "skipped: the other example's service principal is not configured")


def cross_app_cases(ctx: SuiteContext, fx: ExampleFixtures) -> list[CaseResult]:
    case_id, want = "cross_app/other-application", "denied"
    if ctx.other_provider is None:
        return [_skipped(case_id, "cross_app", want)]
    persona, view = _target(fx)
    try:
        n, sid = _count(ctx.sp_runner(persona.claim, ctx.other_provider), f"SELECT count(*) FROM {ctx.view(view)}")
        return [CaseResult(case_id, "cross_app", persona.id, False, want, f"query ran and returned {n} rows", sid)]
    except StatementError as e:
        return [CaseResult(case_id, "cross_app", persona.id, e.is_denied_or_hidden, want, _err(e), e.statement_id)]


def _has_use_catalog(ctx: SuiteContext, principal: str) -> bool:
    res = ctx.admin.execute(f"SHOW GRANTS `{principal}` ON CATALOG `{ctx.catalog}`")
    return any("USE CATALOG" in " ".join(str(v) for v in row).upper().replace("_", " ") for row in res.rows)


def binding_case(ctx: SuiteContext, fx: ExampleFixtures) -> list[CaseResult]:
    case_id, want = "binding/mistaken-grant", "0 rows: the view answers only for its own service principal"
    if ctx.other_provider is None:
        return [_skipped(case_id, "binding", want)]
    persona, view = _target(fx)
    sp = f"`{ctx.other_provider.client_id}`"
    view_fq = ctx.view(view)
    grants = [] if _has_use_catalog(ctx, ctx.other_provider.client_id) else [f"GRANT USE CATALOG ON CATALOG `{ctx.catalog}` TO {sp}"]
    grants += [f"GRANT USE SCHEMA ON SCHEMA `{ctx.catalog}`.`{ctx.example.schemas['portal']}` TO {sp}",
               f"GRANT SELECT ON VIEW {view_fq} TO {sp}"]
    granted = []
    try:
        for stmt in grants:
            ctx.admin.execute(stmt)
            granted.append(stmt)
        n, sid = _count(ctx.sp_runner(persona.claim, ctx.other_provider), f"SELECT count(*) FROM {view_fq}")
        return [CaseResult(case_id, "binding", persona.id, n == 0, want, f"{n} rows", sid)]
    except StatementError as e:
        return [CaseResult(case_id, "binding", persona.id, None, want, f"inconclusive: {_err(e)}", e.statement_id)]
    finally:
        for stmt in reversed(granted):
            ctx.admin.execute(stmt.replace("GRANT ", "REVOKE ", 1).replace(" TO ", " FROM ", 1))


def _b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj, separators=(",", ":")).encode()).rstrip(b"=").decode()


def tamper_claim(token: str, new_claim: str) -> str:
    header, _, signature = token.split(".")
    payload = decode_jwt_unverified(token)["payload"]
    payload["custom"] = {**payload.get("custom", {}), "claim": new_claim}
    return f"{header}.{_b64(payload)}.{signature}"


def alg_none(token: str) -> str:
    return f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(decode_jwt_unverified(token)['payload'])}."


def corrupt_signature(token: str) -> str:
    header, payload, signature = token.split(".")
    return f"{header}.{payload}.{signature[:-4]}{'BBBB' if signature.endswith('AAAA') else 'AAAA'}"


def token_cases(ctx: SuiteContext, fx: ExampleFixtures) -> list[CaseResult]:
    persona = fx.personas[0]
    other = next(p for p in fx.personas if p.claim != persona.claim)
    token, _ = ctx.provider.token_for(persona.claim)
    url = f"{ctx.host}/api/2.0/sql/warehouses/{ctx.warehouse_id}"

    def status(t: str) -> int:
        return ctx.http.get(url, headers={"Authorization": f"Bearer {t}"}, timeout=30).status_code

    baseline = status(token.access_token)
    out = [CaseResult("token/valid-baseline", "token", persona.id, baseline == 200, "HTTP 200", f"HTTP {baseline}")]
    for name, forged in (("edited-claim", tamper_claim(token.access_token, other.claim)),
                         ("unsigned-alg-none", alg_none(token.access_token)),
                         ("corrupted-signature", corrupt_signature(token.access_token))):
        code = status(forged)
        out.append(CaseResult(f"token/{name}", "token", persona.id, code in (400, 401, 403), "rejected (HTTP 400, 401 or 403)",
                              f"HTTP {code}"))
    return out


_NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s?([KkMmBb])?(?!\w)")
_SCALE = {"k": Decimal(1000), "m": Decimal(1_000_000), "b": Decimal(1_000_000_000)}


def numbers_in(text: str) -> list[tuple[Decimal, Decimal]]:
    """(value, tolerance) for every number in text; the tolerance follows the precision shown."""
    out = []
    for m in _NUMBER.finditer(text or ""):
        whole, frac, suffix = m.group(1).replace(",", ""), m.group(2) or "", (m.group(3) or "").lower()
        scale = _SCALE.get(suffix, Decimal(1))
        decimals = len(frac) - 1 if frac else 0
        tol = scale / (Decimal(10) ** decimals) / 2 if (decimals or suffix) else Decimal(1)
        out.append((Decimal(whole + frac) * scale, tol))
    return out


def _cell_numbers(rows) -> list[tuple[Decimal, Decimal]]:
    out = []
    for row in rows:
        for cell in row:
            if isinstance(cell, str):
                try:
                    out.append((Decimal(cell), Decimal("0.005") if "." in cell else Decimal("0.5")))
                except InvalidOperation:
                    out.extend(numbers_in(cell))
    return out


def value_present(value: Decimal, texts, rows) -> bool:
    candidates = [n for t in texts for n in numbers_in(t)] + _cell_numbers(rows)
    return any(abs(c - value) <= tol for c, tol in candidates)


def evaluate_genie(case_id: str, persona_id: str, case: GenieCase, answer: GenieAnswer, values: dict) -> CaseResult:
    expected = f"must {list(case.must)}; must not {list(case.must_not)}"
    if not answer.completed:
        return CaseResult(case_id, "genie", persona_id, None, expected, f"inconclusive: Genie status {answer.status}")
    texts = list(answer.text) + [q.description or "" for q in answer.queries]
    rows = [row for q in answer.queries for row in q.rows]
    sid = ",".join(answer.statement_ids) or None
    leaked = [k for k in case.must_not if value_present(values[k], texts, rows)]
    if leaked:
        return CaseResult(case_id, "genie", persona_id, False, expected, f"LEAKED {leaked}", sid)
    missing = [k for k in case.must if not value_present(values[k], texts, rows)]
    if missing:
        return CaseResult(case_id, "genie", persona_id, None, expected,
                          f"no leak; expected value not found {missing} (answer quality)", sid)
    return CaseResult(case_id, "genie", persona_id, True, expected, "expected values present; no other user's values", sid)


def _conversation_binding(ctx: SuiteContext, fx: ExampleFixtures) -> CaseResult:
    a, b = fx.personas[0], fx.personas[1]
    want = "readable by another claim from the same service principal, so the backend must bind conversation ids to users"
    owner = ctx.genie(a.claim)
    answer = owner.ask(a.genie[0].question if a.genie else "What can I see?")
    try:
        ctx.genie(b.claim).get_message(answer.conversation_id, answer.message_id)
        readable = True
    except GenieError:
        readable = False
    finally:
        try:
            owner.delete_conversation(answer.conversation_id)
        except GenieError:
            pass
    return CaseResult("documented/conversation-binding", "documented", b.id, readable, want, "readable" if readable else "not readable")


def genie_cases(ctx: SuiteContext, fx: ExampleFixtures) -> list[CaseResult]:
    if not ctx.include_genie:
        return []
    if not ctx.genie_space_id:
        return [CaseResult("genie/agent", "genie", None, None, "a Genie Agent id", "skipped: no Genie Agent id")]
    out = []
    for p in fx.personas:
        client = ctx.genie(p.claim)
        for i, case in enumerate(p.genie, 1):
            case_id = f"genie/{p.id}/{i}"
            try:
                answer = client.ask(case.question)
            except GenieError as e:
                out.append(CaseResult(case_id, "genie", p.id, None, "an answer", _err(e)))
                continue
            try:
                out.append(evaluate_genie(case_id, p.id, case, answer, fx.genie_values))
            finally:
                try:
                    client.delete_conversation(answer.conversation_id)
                except GenieError:
                    pass
    out.append(_conversation_binding(ctx, fx))
    return out


SUITE = (visibility_cases, role_effect_cases, attack_cases, privilege_cases, cross_app_cases, binding_case, token_cases, genie_cases)


def run_suite(ctx: SuiteContext, fixtures: ExampleFixtures | None = None) -> list[CaseResult]:
    fx = fixtures or load_fixtures(ctx.example)
    results: list[CaseResult] = []
    for case_fn in SUITE:
        results.extend(case_fn(ctx, fx))
    return results


def failures(results: list[CaseResult]) -> list[CaseResult]:
    return [r for r in results if r.passed is False and r.category != "documented"]


def summarize(results: list[CaseResult]) -> str:
    lines = []
    for cat in CATEGORIES:
        rs = [r for r in results if r.category == cat]
        if rs:
            lines.append(f"{cat:<12} pass {sum(r.passed is True for r in rs):>3}   fail {sum(r.passed is False for r in rs):>3}   "
                         f"inconclusive {sum(r.passed is None for r in rs):>3}")
    for r in results:
        if r.passed is not True:
            tag = "NOTE" if r.category == "documented" or r.passed is None else "FAIL"
            lines.append(f"  {tag} {r.case_id}: expected {r.expected}; observed {r.observed}")
    return "\n".join(lines)


def results_as_dicts(results: list[CaseResult]) -> list[dict]:
    return [asdict(r) for r in results]


def build_local_context(example_name: str, *, include_genie: bool = True) -> SuiteContext:
    from .genie_space import find_space_by_title, space_title
    from .local import LocalEnv, admin_client, read_env

    env = LocalEnv.from_mapping(read_env())
    ex = load_example(example_name)
    creds = env.examples[example_name]
    w = admin_client(env.admin_profile)
    other = next((c for n, c in env.examples.items() if n != example_name), None)
    space_id = creds.genie_space_id or find_space_by_title(w.api_client.do, space_title(ex.load_yaml("genie.yml"), env.catalog))
    return SuiteContext(
        example=ex, catalog=env.catalog, host=env.host, warehouse_id=env.warehouse_id,
        provider=ClaimTokenProvider(env.host, creds.client_id, creds.client_secret),
        admin=StatementRunner(env.host, env.warehouse_id, w.config.authenticate),
        other_provider=ClaimTokenProvider(env.host, other.client_id, other.client_secret) if other else None,
        genie_space_id=space_id, include_genie=include_genie)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the isolation suite against a deployed example")
    parser.add_argument("--example", required=True, choices=("northwind", "larkspur"))
    parser.add_argument("--no-genie", action="store_true")
    parser.add_argument("--evidence", type=Path, help="write scrubbed JSON evidence into this directory")
    args = parser.parse_args(argv)
    ctx = build_local_context(args.example, include_genie=not args.no_genie)
    results = run_suite(ctx)
    print(summarize(results))
    if args.evidence:
        from .evidence import write_evidence
        write_evidence(ctx, results, args.evidence)
    return 1 if failures(results) else 0


if __name__ == "__main__":
    sys.exit(main())
