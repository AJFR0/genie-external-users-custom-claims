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


from claims_kit.config import load_example as _load_example
from claims_kit.sql import split_sql as _split

_LK = _load_example("larkspur")
_V = _LK.template_values("c", "sp", "owner")


def _view_sql(key, name):
    return next(s for s in _split(_LK.read_sql(key, _V)) if f".{name}" in s.split("(")[0] or f".{name}\n" in s)


def test_spend_summary_reads_precomputed_cells_not_claims():
    sql = _view_sql("portal_views", "sponsor_spend_summary")
    assert "sponsor_spend_cells" in sql and "pharmacy_claims" not in sql
    assert "c.members >= ms.min_cell_size" in sql


def test_cells_are_rebuilt_with_the_smallest_role_threshold_as_a_floor():
    sql = _LK.read_sql("derived_tables", _V)
    assert "INSERT OVERWRITE `c`.`larkspur_base`.sponsor_spend_cells" in sql
    assert "min(min_cell_size)" in sql and "role_policies" in sql and "claim_status = 'paid'" in sql


def test_household_is_a_governance_table_and_my_members_reads_it():
    derived = _LK.read_sql("derived_tables", _V)
    assert "CREATE OR REPLACE TABLE `c`.`larkspur_governance`.household" in derived
    policy_members = _view_sql("policy_views", "policy_members")
    assert "`larkspur_governance`.household" in policy_members and "`larkspur_base`.members" not in policy_members


def test_side_channel_probe_values_sit_only_outside_the_persona_scope():
    from examples.larkspur import expectations
    data = generate()
    probes = {p.id: p for p in expectations.side_channel_probes(data)}
    assert set(probes) == {"priya-member-in-my_claims", "ana-spouse-claim-in-my_claims",
                           "priya-other-pharmacy-in-pharmacy_remittance", "theo-cell-in-sponsor_spend_summary",
                           "dana-sponsor-in-sponsor_spend_summary"}
    assert not any(c["member_id"] == "M-9999" for c in data["pharmacy_claims"])
    claims = data["pharmacy_claims"]

    spouse = probes["ana-spouse-claim-in-my_claims"]
    paid = dict(spouse.match)["plan_paid"]
    owners = {c["member_id"] for c in claims if str(c["plan_paid"]) == paid}
    assert owners and not owners & household(data, "M-1001")
    assert not any(str(c["plan_paid"]) == dict(spouse.absent)["plan_paid"] for c in claims)

    other = probes["priya-other-pharmacy-in-pharmacy_remittance"]
    claim = next(c for c in claims if c["claim_id"] == dict(other.match)["claim_id"])
    assert claim["pharmacy_id"] != "PH-0007" and other.error == "CAST_INVALID_INPUT"

    theo = probes["theo-cell-in-sponsor_spend_summary"]
    key = (dict(theo.match)["sponsor_id"], dict(theo.match)["fill_quarter"], dict(theo.match)["drug_class"])
    members = expectations._cell_members(data, {"SPN-ALDER", "SPN-BIRCH"})
    assert 11 <= len(members[key]) < 20, "visible to an 11-member role, hidden from Theo's 20"
    absent_key = (dict(theo.absent)["sponsor_id"], dict(theo.absent)["fill_quarter"], dict(theo.absent)["drug_class"])
    assert absent_key not in members

    dana = probes["dana-sponsor-in-sponsor_spend_summary"]
    names = {s["sponsor_id"]: s["sponsor_name"] for s in data["sponsors"]}
    assert dict(dana.match)["sponsor_name"] == names["SPN-BIRCH"]
    assert dict(dana.absent)["sponsor_name"] not in names.values()


def test_cell_floor_counts_aggregate_roles_only():
    """Review #3: roles without a minimum (members, pharmacies) have min_cell_size 0 and must not lower the floor."""
    sql = _LK.read_sql("derived_tables", _V)
    floor = sql.split("HAVING", 1)[1]
    assert "detail_level = 'aggregate'" in floor


def test_priya_probe_targets_a_raw_member_id_at_her_pharmacy():
    from examples.larkspur import expectations
    data = generate()
    p = {x.id: x for x in expectations.side_channel_probes(data)}["priya-member-in-my_claims"]
    member = dict(p.match)["member_id"]
    assert any(c["member_id"] == member and c["pharmacy_id"] == "PH-0007" for c in data["pharmacy_claims"])



def test_pharmacy_staff_read_precomputed_references_never_raw_member_ids():
    derived = _LK.read_sql("derived_tables", _V)
    remit = derived[derived.index("pharmacy_remittance_rows"):]
    assert "sha2(concat('larkspur-demo:', c.member_id), 256)" in remit and "c.member_id," not in remit
    view = _view_sql("portal_views", "pharmacy_remittance")
    assert "pharmacy_remittance_rows" in view and "pharmacy_claims" not in view
