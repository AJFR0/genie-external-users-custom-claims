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
