import re

import pytest

from claims_kit.config import load_example
from claims_kit.sql import split_sql


@pytest.mark.parametrize("name", ["northwind", "larkspur"])
def test_claim_format_constraint_is_fully_anchored(name):
    # Java regex `$` also matches before a trailing newline, so RLIKE '^...$' would accept 'pu-1001\n'.
    sql = load_example(name).sql["governance"].read_text()
    code = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    assert "RLIKE" not in code
    assert "regexp_extract(portal_user_id, '^[a-z0-9][a-z0-9._:-]{0,127}', 0) = portal_user_id" in sql


def test_roster_balances_are_scoped_to_the_plan():
    # A participant can hold money in several plans; a plan's roster must only show money in that plan.
    sql = load_example("northwind").sql["portal_views"].read_text()
    roster = sql[sql.index("plan_roster ("):]
    assert "GROUP BY participant_id, plan_id" in roster
    assert "b.participant_id = p.participant_id AND b.plan_id = p.plan_id" in roster


def _functions(name):
    ex = load_example(name)
    text = ex.read_sql("policy_functions", ex.template_values("c", "sp-app-id", "owner"))
    return ex, {re.search(r"`\.`?(rf_\w+)`?\s*\(", s).group(1): s for s in split_sql(text)}


def test_policy_functions_match_the_definitions():
    for name in ("northwind", "larkspur"):
        ex, fns = _functions(name)
        assert list(fns) == list(ex.claim_functions)
        for rp in (r for r in ex.row_policies if r.function):
            params = re.search(r"\((.*?)\)\s*RETURNS", fns[rp.function], re.S).group(1)
            assert len(re.findall(r"(p_\w+)\s+\w+", params)) == len(rp.columns), f"{name}.{rp.function}"


def test_policy_functions_read_only_governance_objects():
    """Unity Catalog rejects a policy function that reads a table with its own policy, so none reads a base table."""
    for name in ("northwind", "larkspur"):
        ex, fns = _functions(name)
        for fn, sql in fns.items():
            assert "current_oauth_custom_identity_claim()" not in sql, fn
            assert f"`{ex.schemas['base']}`" not in sql, fn
            if fn != "rf_deny":
                assert "my_effective_grants" in sql or "my_members" in sql, fn


def test_deny_function_returns_false():
    for name in ("northwind", "larkspur"):
        _, fns = _functions(name)
        assert fns["rf_deny"].rstrip().endswith("RETURN false")
