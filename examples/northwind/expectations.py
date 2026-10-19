"""Independent oracle: what each Northwind persona must see, computed from the generated data."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from claims_kit.personas import ViewExpect

ACCESS = ("role", "scope_id")
PARTICIPANT = ("participant_id",)
PLAN = ("plan_id",)


def _empty() -> dict[str, ViewExpect]:
    none = frozenset()
    return {"my_access": ViewExpect(ACCESS, none), "my_accounts": ViewExpect(PARTICIPANT, none),
            "my_contributions": ViewExpect(PARTICIPANT, none), "plan_summary": ViewExpect(PLAN, none),
            "plan_roster": ViewExpect(PARTICIPANT, none)}


def view_expectations(data: dict) -> dict[str, dict[str, ViewExpect]]:
    def in_plans(*plans):
        return frozenset(p["participant_id"] for p in data["participants"] if p["plan_id"] in plans)

    def participant(pid, *access):
        e = _empty()
        e["my_access"] = ViewExpect(ACCESS, frozenset(access))
        e["my_accounts"] = ViewExpect(PARTICIPANT, frozenset({pid}))
        e["my_contributions"] = ViewExpect(PARTICIPANT, frozenset({pid}))
        return e

    linda = participant("P-2001", "sponsor|PLAN-A", "participant|P-2001")
    linda["plan_summary"] = ViewExpect(PLAN, frozenset({"PLAN-A"}))
    linda["plan_roster"] = ViewExpect(PARTICIPANT, in_plans("PLAN-A"), not_null_columns=("date_of_birth",))
    raj = _empty()
    raj["my_access"] = ViewExpect(ACCESS, frozenset({"advisor|PLAN-A", "advisor|PLAN-C"}))
    raj["plan_summary"] = ViewExpect(PLAN, frozenset({"PLAN-A", "PLAN-C"}))
    raj["plan_roster"] = ViewExpect(PARTICIPANT, in_plans("PLAN-A", "PLAN-C"), null_columns=("date_of_birth",))
    return {"maya": participant("P-1001", "participant|P-1001"), "james": participant("P-1002", "participant|P-1002"),
            "linda": linda, "raj": raj, "unknown": _empty()}


def genie_values(data: dict) -> dict[str, Decimal]:
    by_participant, by_plan = defaultdict(Decimal), defaultdict(Decimal)
    for b in data["account_balances"]:
        by_participant[b["participant_id"]] += b["balance"]
        by_plan[b["plan_id"]] += b["balance"]
    return {"maya_total_balance": by_participant["P-1001"], "james_total_balance": by_participant["P-1002"],
            "linda_total_balance": by_participant["P-2001"], "plan_a_total": by_plan["PLAN-A"],
            "plan_b_total": by_plan["PLAN-B"], "plan_c_total": by_plan["PLAN-C"]}
