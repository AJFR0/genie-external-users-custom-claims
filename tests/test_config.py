import pytest

from claims_kit.config import SQL_KEYS, load_example


@pytest.mark.parametrize("name,prefix", [("northwind", "pu-"), ("larkspur", "rx-")])
def test_examples_load(name, prefix):
    ex = load_example(name)
    assert ex.claim_prefix == prefix and set(ex.sql) == set(SQL_KEYS)
    assert ex.claim_views[0] == "governance.my_effective_grants"
    assert "my_access" in ex.portal_views and not set(ex.portal_views) & {v.split(".")[1] for v in ex.public_views}


def test_fq_and_template_values():
    ex = load_example("northwind")
    assert ex.fq("cat", "governance.my_effective_grants") == "`cat`.`northwind_governance`.`my_effective_grants`"
    assert ex.template_values("cat", "app-id", "me@example.com") == {
        "catalog": "cat", "base": "northwind_base", "gov": "northwind_governance", "portal": "northwind_portal",
        "portal_sp": "app-id", "view_owner": "me@example.com", "portal_group": "genie-claims-ref-northwind-portal-backends"}


def test_unknown_example():
    with pytest.raises(FileNotFoundError):
        load_example("nope")


import re

from claims_kit.config import IDENTITY_PREFIX, RowPolicy, parse_row_policies
from claims_kit.tags import load_tag_set


def test_row_policies_keep_argument_order():
    rp = next(r for r in load_example("larkspur").row_policies if r.table == "base.pharmacy_claims")
    assert (rp.grain, rp.function, rp.schema) == ("claims", "rf_claims", "base")
    assert rp.columns == (("member_id", "member"), ("pharmacy_id", "pharmacy"))


def test_every_grain_and_key_exists_in_the_tag_file():
    tags = load_tag_set("governed")
    for name in ("northwind", "larkspur"):
        for rp in load_example(name).row_policies:
            tags.grain(rp.grain)
            for _, key in rp.columns:
                tags.key(key)


def test_one_filter_policy_per_schema_and_grain():
    for name in ("northwind", "larkspur"):
        pairs = [(rp.schema, rp.grain) for rp in load_example(name).row_policies if rp.function]
        assert len(pairs) == len(set(pairs))


def test_every_base_table_a_portal_view_reads_has_a_row_policy():
    """The repo's own guard against the F1 mistake: a base table read by a portal view but left unprotected."""
    for name in ("northwind", "larkspur"):
        ex = load_example(name)
        covered = {rp.table for rp in ex.row_policies}
        text = "".join(ex.sql[k].read_text() for k in ("policy_views", "portal_views", "public_views"))
        read = {f"base.{t}" for t in re.findall(r"\{\{base\}\}`\.(\w+)", text)}
        assert read <= covered, f"{name}: no row policy for {sorted(read - covered)}"


def test_governance_tables_are_policy_inputs_without_policies():
    """Unity Catalog rejects a policy function that reads a table with its own policy, so governance stays unprotected."""
    for name in ("northwind", "larkspur"):
        assert all(rp.schema == "base" for rp in load_example(name).row_policies)


def test_portal_group_and_template_value():
    ex = load_example("northwind")
    assert ex.portal_group == f"{IDENTITY_PREFIX}-northwind-portal-backends"
    assert ex.template_values("c", "sp", "me")["portal_group"] == ex.portal_group


def test_policy_with_function_needs_columns():
    with pytest.raises(ValueError, match="columns"):
        parse_row_policies([{"table": "base.t", "grain": "accounts", "function": "rf_t"}])


def test_reference_table_has_no_function_or_columns():
    assert parse_row_policies([{"table": "base.funds", "grain": "reference"}]) == (RowPolicy("base.funds", "reference", None, ()),)


def test_drills_name_a_protected_table_and_a_portal_view():
    for name in ("northwind", "larkspur"):
        ex = load_example(name)
        rp = next(r for r in ex.row_policies if r.table == ex.drills["table"])
        assert ex.drills["key_column"] in dict(rp.columns) and ex.drills["view"] in ex.portal_views


from claims_kit.config import ColumnMask


def test_aggregate_and_roster_roles_never_reach_member_balance_rows():
    """Review #1: a policy admits only rows some view exposes at that granularity, so sponsors and advisors read
    precomputed totals and the balances table admits the participant's own rows only."""
    ex = load_example("northwind")
    rp = next(r for r in ex.row_policies if r.table == "base.account_balances")
    assert rp.columns == (("participant_id", "member"),)
    assert {"base.plan_fund_balances", "base.participant_plan_balances"} <= {r.table for r in ex.row_policies}


def test_masks_live_in_the_policy_layer():
    nw, lk = load_example("northwind"), load_example("larkspur")
    assert nw.column_masks == (ColumnMask("base.participants", "roster", "cm_date_of_birth", ("date_of_birth", "birth_date"),
                                          (("plan_id", "tenant"),)),)
    assert lk.column_masks[0].table == "base.pharmacy_claims" and lk.column_masks[0].column == ("member_id", "member")
    for ex in (nw, lk):
        for m in ex.column_masks:
            assert m.function in ex.claim_functions
