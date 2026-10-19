from decimal import Decimal

from examples.larkspur.expectations import genie_values, household
from examples.larkspur.generate import generate


def test_deterministic():
    assert generate() == generate()


def test_household_rule_inputs():
    data = generate()
    assert household(data, "M-1001") == frozenset({"M-1001", "M-1003"})
    members = {m["member_id"]: m for m in data["members"]}
    assert members["M-1002"]["relationship"] == "spouse" and members["M-1004"]["relationship"] == "child"


def test_every_persona_member_has_paid_claims():
    paid = {c["member_id"] for c in generate()["pharmacy_claims"] if c["claim_status"] == "paid"}
    assert {"M-1001", "M-1002", "M-1003", "M-1004", "M-2001"} <= paid


def test_suppression_changes_the_numbers():
    v = genie_values(generate())
    assert v["alder_total_plan_paid"] > v["alder_visible_plan_paid_11"] > v["alder_visible_plan_paid_20"] > 0
    assert (v["alder_total_plan_paid"] - v["alder_visible_plan_paid_11"]) / v["alder_total_plan_paid"] > Decimal("0.05")
    assert (v["alder_visible_plan_paid_11"] - v["alder_visible_plan_paid_20"]) / v["alder_visible_plan_paid_11"] > Decimal("0.05")


def test_integrity():
    data = generate()
    ids = [c["claim_id"] for c in data["pharmacy_claims"]]
    members = {m["member_id"] for m in data["members"]}
    ndcs = {d["ndc"] for d in data["drugs"]}
    assert len(ids) == len(set(ids)) and sum(c["pharmacy_id"] == "PH-0007" for c in data["pharmacy_claims"]) >= 20
    assert all(c["member_id"] in members and c["ndc"] in ndcs for c in data["pharmacy_claims"])
    assert len(data["accumulators"]) == len(members)
