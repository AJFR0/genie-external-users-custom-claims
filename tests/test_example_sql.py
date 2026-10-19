import pytest

from claims_kit.config import load_example


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
