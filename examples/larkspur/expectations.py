"""Independent oracle: what each Larkspur persona must see, computed from the generated data."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from claims_kit.personas import SideChannelProbe, ViewExpect

ACCESS = ("role", "scope_id")
MEMBER = ("member_id",)
CELL = ("sponsor_id", "fill_quarter", "drug_class")
CLAIM = ("claim_id",)


def _empty() -> dict[str, ViewExpect]:
    none = frozenset()
    return {"my_access": ViewExpect(ACCESS, none), "my_claims": ViewExpect(MEMBER, none), "my_accumulators": ViewExpect(MEMBER, none),
            "sponsor_spend_summary": ViewExpect(CELL, none), "pharmacy_remittance": ViewExpect(CLAIM, none)}


def _is_minor(dob: date, today: date | None = None) -> bool:
    today = today or date.today()  # the view uses current_date(), so the oracle does too
    try:
        cutoff = today.replace(year=today.year - 18)
    except ValueError:
        cutoff = today.replace(year=today.year - 18, day=28)
    return dob > cutoff


def household(data: dict, subscriber_id: str) -> frozenset:
    """The subscriber plus their children under 18. Spouses and adult children are never included."""
    return frozenset({subscriber_id} | {m["member_id"] for m in data["members"] if m["subscriber_id"] == subscriber_id
                                        and m["relationship"] == "child" and _is_minor(m["date_of_birth"])})


def _quarter(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def _cell_members(data: dict, sponsors) -> dict:
    drug_class = {d["ndc"]: d["drug_class"] for d in data["drugs"]}
    members = defaultdict(set)
    for c in data["pharmacy_claims"]:
        if c["claim_status"] == "paid" and c["sponsor_id"] in sponsors:
            members[(c["sponsor_id"], _quarter(c["fill_date"]), drug_class[c["ndc"]])].add(c["member_id"])
    return members


def cells(data: dict, sponsors, min_cell: int) -> set:
    return {k for k, v in _cell_members(data, sponsors).items() if len(v) >= min_cell}


def _plan_paid_in(data: dict, keys: set) -> Decimal:
    drug_class = {d["ndc"]: d["drug_class"] for d in data["drugs"]}
    return sum((c["plan_paid"] for c in data["pharmacy_claims"] if c["claim_status"] == "paid"
                and (c["sponsor_id"], _quarter(c["fill_date"]), drug_class[c["ndc"]]) in keys), Decimal(0))


def view_expectations(data: dict) -> dict[str, dict[str, ViewExpect]]:
    def member(access, members):
        e = _empty()
        e["my_access"] = ViewExpect(ACCESS, frozenset(access))
        e["my_claims"] = ViewExpect(MEMBER, members)
        e["my_accumulators"] = ViewExpect(MEMBER, members)
        return e

    ana = member({"subscriber|M-1001"}, household(data, "M-1001"))
    marco = member({"member|M-1002"}, frozenset({"M-1002"}))
    dana = member({"subscriber|M-2001", "sponsor_admin|SPN-ALDER"}, household(data, "M-2001"))
    dana["sponsor_spend_summary"] = ViewExpect(CELL, frozenset("|".join(k) for k in cells(data, {"SPN-ALDER"}, 11)))
    theo = _empty()
    theo["my_access"] = ViewExpect(ACCESS, frozenset({"consultant|SPN-ALDER", "consultant|SPN-BIRCH"}))
    theo["sponsor_spend_summary"] = ViewExpect(CELL, frozenset("|".join(k) for k in cells(data, {"SPN-ALDER", "SPN-BIRCH"}, 20)))
    priya = _empty()
    priya["my_access"] = ViewExpect(ACCESS, frozenset({"pharmacy|PH-0007"}))
    priya["pharmacy_remittance"] = ViewExpect(
        CLAIM, frozenset(c["claim_id"] for c in data["pharmacy_claims"] if c["pharmacy_id"] == "PH-0007"),
        never_equal=("member_ref", frozenset(m["member_id"] for m in data["members"])))
    return {"ana": ana, "marco": marco, "dana": dana, "theo": theo, "priya": priya, "unknown": _empty()}


def genie_values(data: dict) -> dict[str, Decimal]:
    paid = [c for c in data["pharmacy_claims"] if c["claim_status"] == "paid"]

    def member_paid(ids):
        return sum((c["member_paid"] for c in paid if c["member_id"] in ids), Decimal(0))

    def sponsor_plan_paid(sponsor):
        return sum((c["plan_paid"] for c in paid if c["sponsor_id"] == sponsor), Decimal(0))

    return {
        "ana_household_member_paid": member_paid(household(data, "M-1001")),
        "marco_member_paid": member_paid({"M-1002"}),
        "noah_member_paid": member_paid({"M-1004"}),
        "dana_member_paid": member_paid({"M-2001"}),
        "alder_total_plan_paid": sponsor_plan_paid("SPN-ALDER"),
        "alder_visible_plan_paid_11": _plan_paid_in(data, cells(data, {"SPN-ALDER"}, 11)),
        "alder_visible_plan_paid_20": _plan_paid_in(data, cells(data, {"SPN-ALDER"}, 20)),
        "cedar_total_plan_paid": sponsor_plan_paid("SPN-CEDAR"),
        "priya_pharmacy_plan_paid": sum((c["plan_paid"] for c in paid if c["pharmacy_id"] == "PH-0007"), Decimal(0)),
    }


def _absent_money(values) -> Decimal:
    """The smallest x.01 amount that appears in no row, so a probe for it can only ever match nothing."""
    n = 1
    while Decimal(f"{n}.01") in values:
        n += 1
    return Decimal(f"{n}.01")


def side_channel_probes(data: dict) -> list[SideChannelProbe]:
    """Error probes: each value exists only in rows the persona may not see, and each control value exists nowhere."""
    claims = data["pharmacy_claims"]
    ana_visible = household(data, "M-1001")
    ana_paid = {c["plan_paid"] for c in claims if c["member_id"] in ana_visible}
    spouse_paid = min(c["plan_paid"] for c in claims if c["member_id"] == "M-1002" and c["plan_paid"] not in ana_paid)
    other_pharmacy_claim = min(c["claim_id"] for c in claims if c["pharmacy_id"] != "PH-0007")
    members = _cell_members(data, {"SPN-ALDER", "SPN-BIRCH"})
    theo_hidden = min(k for k, v in members.items() if 11 <= len(v) < 20 and "(" not in k[2])
    names = {s["sponsor_id"]: s["sponsor_name"] for s in data["sponsors"]}
    cell = (("sponsor_id", theo_hidden[0]), ("fill_quarter", theo_hidden[1]), ("drug_class", theo_hidden[2]))
    pharmacy_member = min(c["member_id"] for c in claims if c["pharmacy_id"] == "PH-0007")
    return [
        SideChannelProbe("priya-member-in-my_claims", "priya", "my_claims",
                         (("member_id", pharmacy_member),), (("member_id", "M-9999"),), error="CAST_INVALID_INPUT",
                         source="a raw member id at her own pharmacy; pharmacy staff see one-way references only"),
        SideChannelProbe("ana-spouse-claim-in-my_claims", "ana", "my_claims",
                         (("plan_paid", str(spouse_paid)),), (("plan_paid", str(_absent_money({c["plan_paid"] for c in claims}))),),
                         source="her spouse's claim; adult household members stay private"),
        SideChannelProbe("priya-other-pharmacy-in-pharmacy_remittance", "priya", "pharmacy_remittance",
                         (("claim_id", other_pharmacy_claim),), (("claim_id", "C-999999"),), error="CAST_INVALID_INPUT",
                         source="a claim filled at another pharmacy"),
        SideChannelProbe("theo-cell-in-sponsor_spend_summary", "theo", "sponsor_spend_summary",
                         cell, cell[:2] + (("drug_class", "No such class"),), error="CAST_INVALID_INPUT",
                         source="a spend group below Theo's minimum group size of 20"),
        SideChannelProbe("dana-sponsor-in-sponsor_spend_summary", "dana", "sponsor_spend_summary",
                         (("sponsor_name", names["SPN-BIRCH"]),), (("sponsor_name", "No Such Sponsor"),),
                         source="a sponsor Dana has no grant for; the client list stays private"),
    ]
