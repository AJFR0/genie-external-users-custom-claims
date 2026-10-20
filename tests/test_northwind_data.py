from decimal import Decimal

from examples.northwind.generate import generate


def test_generate_is_deterministic():
    assert generate() == generate()


def test_personas_exist_with_balances_and_contributions():
    data = generate()
    parts = {p["participant_id"]: p for p in data["participants"]}
    assert (parts["P-1001"]["plan_id"], parts["P-1002"]["plan_id"], parts["P-2001"]["plan_id"]) == ("PLAN-A", "PLAN-A", "PLAN-B")
    for pid in ("P-1001", "P-1002", "P-2001"):
        assert any(b["participant_id"] == pid and b["balance"] > 0 for b in data["account_balances"])
        assert sum(1 for c in data["contributions"] if c["participant_id"] == pid) == 18


def test_referential_integrity_and_unique_ids():
    data = generate()
    plan_ids = {p["plan_id"] for p in data["plans"]}
    fund_ids = {f["fund_id"] for f in data["funds"]}
    pids = [p["participant_id"] for p in data["participants"]]
    assert len(pids) == len(set(pids)) == 150
    assert all(p["plan_id"] in plan_ids for p in data["participants"])
    assert all(b["fund_id"] in fund_ids and b["participant_id"] in set(pids) for b in data["account_balances"])
    assert all(isinstance(b["balance"], Decimal) for b in data["account_balances"])


def test_participant_plans_mapping_is_derived_into_governance():
    from claims_kit.config import load_example
    ex = load_example("northwind")
    sql = ex.read_sql("derived_tables", ex.template_values("c", "sp", "owner"))
    assert "CREATE OR REPLACE TABLE `c`.`northwind_governance`.participant_plans" in sql
    assert "FROM `c`.`northwind_base`.account_balances" in sql and "FROM `c`.`northwind_base`.contributions" in sql


def test_entitlements_notebook_builds_the_derived_tables():
    from pathlib import Path
    nb = (Path(__file__).resolve().parents[1] / "notebooks" / "03_entitlements.py").read_text()
    assert 'read_sql("derived_tables"' in nb


def _probes():
    from examples.northwind import expectations, generate
    data = generate.generate()
    return data, {p.id: p for p in expectations.side_channel_probes(data)}


def test_side_channel_probe_values_sit_only_outside_the_persona_scope():
    data, probes = _probes()
    assert set(probes) == {"maya-balance-in-my_accounts", "raj-participant-in-plan_roster", "maya-grant-in-my_access",
                           "linda-contribution-in-my_contributions"}
    bal = probes["maya-balance-in-my_accounts"]
    value = dict(bal.match)["balance"]
    owners = {r["participant_id"] for r in data["account_balances"] if str(r["balance"]) == value}
    assert owners and "P-1001" not in owners
    assert not any(str(r["balance"]) == dict(bal.absent)["balance"] for r in data["account_balances"])

    roster = probes["raj-participant-in-plan_roster"]
    pid = dict(roster.match)["participant_id"]
    assert roster.error == "CAST_INVALID_INPUT"
    assert any(r["participant_id"] == pid and r["plan_id"] == "PLAN-B" for r in data["participants"])
    assert not any(r["participant_id"] == dict(roster.absent)["participant_id"] for r in data["participants"])

    contrib = probes["linda-contribution-in-my_contributions"]
    amount = dict(contrib.match)["amount"]
    owners = {r["participant_id"] for r in data["contributions"] if str(r["amount"]) == amount}
    assert owners and "P-2001" not in owners
    assert not any(str(r["amount"]) == dict(contrib.absent)["amount"] for r in data["contributions"])

    access = probes["maya-grant-in-my_access"]
    assert dict(access.match) == {"scope_id": "PLAN-A"} and dict(access.absent) == {"scope_id": "PLAN-Z"}
