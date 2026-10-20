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
    ex = load_example("northwind")
    roster = ex.sql["portal_views"].read_text()
    roster = roster[roster.index("plan_roster ("):]
    derived = ex.sql["derived_tables"].read_text()
    assert "GROUP BY participant_id, plan_id" in derived[derived.index("participant_plan_balances"):]
    assert "b.participant_id = p.participant_id AND b.plan_id = p.plan_id" in roster


def _functions(name):
    ex = load_example(name)
    text = ex.read_sql("policy_functions", ex.template_values("c", "sp-app-id", "owner"))
    return ex, {re.search(r"`\.`?((?:rf|cm)_\w+)`?\s*\(", s).group(1): s for s in split_sql(text)}


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
                assert any(v in sql for v in ("my_effective_grants", "policy_members")), fn


def test_deny_function_returns_false():
    for name in ("northwind", "larkspur"):
        _, fns = _functions(name)
        assert fns["rf_deny"].rstrip().endswith("RETURN false")


def _ddl(ex, key, table):
    text = ex.read_sql(key, ex.template_values("c", "sp", "owner"))
    return next(s for s in split_sql(text) if re.search(rf"\.`?{table}`?\s*\(", s.split("\n")[0]))


def test_protected_tables_cluster_on_their_policy_keys_and_grants_on_the_claim():
    for name in ("northwind", "larkspur"):
        ex = load_example(name)
        for rp in (r for r in ex.row_policies if r.function):
            table = rp.table.split(".", 1)[1]
            ddl = _ddl(ex, "base_tables", table)
            cols = ", ".join(c for c, k in rp.columns if k != "cell_count")
            assert f"CLUSTER BY ({cols})" in ddl, f"{name}.{table}"
        assert "CLUSTER BY (portal_user_id)" in _ddl(ex, "governance", "portal_user_grants"), name


def test_mask_functions_take_the_column_then_its_arguments():
    for name in ("northwind", "larkspur"):
        ex, fns = _functions(name)
        for m in ex.column_masks:
            params = re.search(r"\((.*?)\)\s*RETURNS", fns[m.function], re.S).group(1)
            assert len(re.findall(r"(p_\w+)\s+\w+", params)) == 1 + len(m.using), f"{name}.{m.function}"


def test_policy_functions_read_the_policy_household_view_not_the_view_layer_one():
    """Review #5: the view layer reads live members; the policies read the governance copy, so the layers disagree
    toward fewer rows when the copy is stale."""
    _, fns = _functions("larkspur")
    for fn in ("rf_members", "rf_claims", "rf_accumulators"):
        assert "policy_members" in fns[fn] and ".my_members" not in fns[fn], fn
    lk = load_example("larkspur")
    views = split_sql(lk.read_sql("policy_views", lk.template_values("c", "sp", "o")))
    my_members = next(v for v in views if ".my_members" in v.split("\n")[0])
    policy_members = next(v for v in views if ".policy_members" in v.split("\n")[0])
    assert "`larkspur_base`.members" in my_members and "household" in policy_members
