"""Independent oracle: what each Northwind persona must see, computed from the generated data."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from claims_kit.personas import SideChannelProbe, ViewExpect

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


def _absent_money(values) -> Decimal:
    """The smallest x.01 amount that appears in no row, so a probe for it can only ever match nothing."""
    n = 1
    while Decimal(f"{n}.01") in values:
        n += 1
    return Decimal(f"{n}.01")


def side_channel_probes(data: dict) -> list[SideChannelProbe]:
    """Error probes: each value exists only in rows the persona may not see, and each control value exists nowhere."""
    balances = data["account_balances"]
    maya_own = {b["balance"] for b in balances if b["participant_id"] == "P-1001"}
    other_balance = min(b["balance"] for b in balances if b["participant_id"] != "P-1001" and b["balance"] not in maya_own)
    plan_b = min(p["participant_id"] for p in data["participants"] if p["plan_id"] == "PLAN-B")
    contributions = data["contributions"]
    linda_own = {c["amount"] for c in contributions if c["participant_id"] == "P-2001"}
    plan_a_amount = min(c["amount"] for c in contributions
                        if c["plan_id"] == "PLAN-A" and c["participant_id"] != "P-2001" and c["amount"] not in linda_own)
    linda_row = min((b for b in balances if b["plan_id"] == "PLAN-A" and b["participant_id"] != "P-2001"
                     and b["balance"] not in {x["balance"] for x in balances if x["participant_id"] == "P-2001"}),
                    key=lambda b: (b["participant_id"], b["fund_id"]))
    return [
        SideChannelProbe("linda-fund-balance-in-my_accounts", "linda", "my_accounts",
                         (("participant_id", linda_row["participant_id"]), ("balance", str(linda_row["balance"]))),
                         (("participant_id", linda_row["participant_id"]), ("balance", str(_absent_money({b["balance"] for b in balances})))),
                         source="a Plan A participant's per-fund balance; Linda sponsors Plan A but sees only totals"),
        SideChannelProbe("maya-balance-in-my_accounts", "maya", "my_accounts",
                         (("balance", str(other_balance)),), (("balance", str(_absent_money({b["balance"] for b in balances}))),),
                         source="another participant's balance"),
        SideChannelProbe("raj-participant-in-plan_roster", "raj", "plan_roster",
                         (("participant_id", plan_b),), (("participant_id", "P-9999"),), error="CAST_INVALID_INPUT",
                         source="a Plan B participant, outside Raj's plans"),
        SideChannelProbe("maya-grant-in-my_access", "maya", "my_access",
                         (("scope_id", "PLAN-A"),), (("scope_id", "PLAN-Z"),), source="another user's grant"),
        SideChannelProbe("linda-contribution-in-my_contributions", "linda", "my_contributions",
                         (("amount", str(plan_a_amount)),),
                         (("amount", str(_absent_money({c["amount"] for c in contributions}))),),
                         source="a Plan A participant's contribution; Linda sponsors Plan A but never sees contributions"),
    ]
