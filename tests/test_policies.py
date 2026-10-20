from claims_kit.config import load_example
from claims_kit.policies import (DEFAULT_DENY, coverage_problems, coverage_queries, default_deny_sql, drop_statements,
                                 policy_name, policy_sql, policy_statements, tag_statements)
from claims_kit.tags import load_tag_set

NW = load_example("northwind")
LK = load_example("larkspur")
GOV = load_tag_set("governed")
GROUP = NW.portal_group


def _rp(ex, table):
    return next(r for r in ex.row_policies if r.table == table)


def test_tag_statements_tag_each_table_and_policy_column():
    stmts = tag_statements(NW, "c", GOV)
    assert "ALTER TABLE `c`.`northwind_base`.`account_balances` SET TAGS ('portal_grain' = 'accounts')" in stmts
    assert ("ALTER TABLE `c`.`northwind_base`.`participants` ALTER COLUMN `plan_id` "
            "SET TAGS ('portal_key' = 'tenant')") in stmts
    assert "ALTER TABLE `c`.`northwind_base`.`funds` SET TAGS ('portal_grain' = 'reference')" in stmts


def test_policy_sql_binds_columns_by_tag_in_argument_order():
    sql = policy_sql(LK, "c", GOV, _rp(LK, "base.sponsor_spend_cells"), LK.portal_group)
    assert sql.startswith("CREATE OR REPLACE POLICY portal_cells_rows ON SCHEMA `c`.`larkspur_base`")
    assert "ROW FILTER `c`.`larkspur_governance`.`rf_cells`" in sql
    assert f"TO `{LK.portal_group}`" in sql
    assert "FOR TABLES WHEN has_tag_value('portal_grain', 'cells')" in sql
    assert ("MATCH COLUMNS has_tag_value('portal_key', 'tenant') AS tenant, "
            "has_tag_value('portal_key', 'cell_count') AS cell_count") in sql
    assert sql.rstrip().endswith("USING COLUMNS (tenant, cell_count)")


def test_reference_tables_get_tags_but_no_policy():
    stmts = policy_statements(NW, "c", GOV, GROUP)
    assert not any("portal_reference_rows" in s for s in stmts)
    assert sum(s.startswith("CREATE OR REPLACE POLICY portal_") and "_rows " in s for s in stmts) == 6


def test_default_deny_covers_the_base_schema_only():
    deny = [s for s in policy_statements(NW, "c", GOV, GROUP) if DEFAULT_DENY in s]
    assert len(deny) == 1
    assert "ON SCHEMA `c`.`northwind_base`" in deny[0]
    assert "FOR TABLES WHEN NOT (has_tag('portal_grain'))" in deny[0]
    assert "ROW FILTER `c`.`northwind_governance`.`rf_deny`" in deny[0]


def test_stand_in_default_deny_lists_every_grain_key():
    sql = default_deny_sql(NW, "c", load_tag_set("stand_in"), "base", GROUP)
    assert sql.count("has_tag('class.") == 12


def test_drop_statements_name_every_policy_without_if_exists():
    stmts = drop_statements(NW, "c")
    assert f"DROP POLICY {policy_name(_rp(NW, 'base.account_balances'))} ON SCHEMA `c`.`northwind_base`" in stmts
    assert len(stmts) == 8 and sum(DEFAULT_DENY in s for s in stmts) == 1
    assert not any("IF EXISTS" in s for s in stmts)


def test_coverage_queries_read_the_base_schema():
    table_q, column_q = coverage_queries(NW, "c")
    assert "`c`.information_schema.table_tags" in table_q and "IN ('northwind_base')" in table_q
    assert "`c`.information_schema.column_tags" in column_q and "column_name" in column_q


def _tags_ok(ex, tags):
    from claims_kit.policies import _tagged_columns
    trows, crows = [], []
    for full, grain, columns in _tagged_columns(ex):
        logical, table = full.split(".", 1)
        g = tags.grain(grain)
        trows.append((ex.schemas[logical], table, g.key, g.value or ""))
        for col, key in columns:
            k = tags.key(key)
            crows.append((ex.schemas[logical], table, col, k.key, k.value or ""))
    return trows, crows


def test_coverage_is_clean_when_every_tag_is_in_place():
    assert coverage_problems(NW, GOV, *_tags_ok(NW, GOV)) == []
    stand_in = load_tag_set("stand_in")
    assert coverage_problems(NW, stand_in, *_tags_ok(NW, stand_in)) == []


def test_coverage_flags_missing_grain_and_missing_key_column():
    trows, crows = _tags_ok(NW, GOV)
    trows = [r for r in trows if r[1] != "contributions"]
    crows = [r for r in crows if not (r[1] == "account_balances" and r[2] == "participant_id")]
    problems = coverage_problems(NW, GOV, trows, crows)
    assert any("contributions" in p and "grain" in p for p in problems)
    assert any("account_balances.participant_id" in p for p in problems)


def test_coverage_flags_ambiguous_key_column():
    trows, crows = _tags_ok(NW, GOV)
    crows.append(("northwind_base", "account_balances", "fund_id", "portal_key", "member"))
    assert any("ambiguous" in p and "account_balances" in p for p in coverage_problems(NW, GOV, trows, crows))


from claims_kit.policies import expected_policy_names, mask_policy_name, mask_sql, policy_problems


def test_mask_sql_binds_the_masked_column_and_its_arguments():
    sql = mask_sql(NW, "c", GOV, NW.column_masks[0], GROUP)
    assert sql.startswith("CREATE OR REPLACE POLICY portal_roster_birth_date_mask ON SCHEMA `c`.`northwind_base`")
    assert "COLUMN MASK `c`.`northwind_governance`.`cm_date_of_birth`" in sql
    assert "FOR TABLES WHEN has_tag_value('portal_grain', 'roster')" in sql
    assert ("MATCH COLUMNS has_tag_value('portal_key', 'birth_date') AS birth_date, "
            "has_tag_value('portal_key', 'tenant') AS tenant") in sql
    assert "ON COLUMN birth_date" in sql and sql.rstrip().endswith("USING COLUMNS (tenant)")


def test_mask_columns_are_tagged_and_covered():
    stmts = tag_statements(NW, "c", GOV)
    assert ("ALTER TABLE `c`.`northwind_base`.`participants` ALTER COLUMN `date_of_birth` "
            "SET TAGS ('portal_key' = 'birth_date')") in stmts
    assert len(stmts) == len(set(stmts)), "no duplicate tag statements"
    trows, crows = _tags_ok(NW, GOV)
    crows = [r for r in crows if r[2] != "date_of_birth"]
    assert any("date_of_birth" in p for p in coverage_problems(NW, GOV, trows, crows))


def test_policy_problems_compare_deployed_policies_with_the_enforcement_model():
    names = expected_policy_names(NW)
    assert mask_policy_name(NW.column_masks[0]) in names and DEFAULT_DENY in names
    assert policy_problems(NW, names, "layered") == []
    assert any("missing" in p for p in policy_problems(NW, names[1:], "layered"))
    assert policy_problems(NW, [], "views") == []
    assert any("views" in p for p in policy_problems(NW, names[:1], "views"))


def test_stale_portal_policies_are_dropped_and_others_left_alone():
    from claims_kit.policies import stale_policy_statements
    deployed = expected_policy_names(LK) + ["portal_claims_member_mask", "finance_team_policy"]
    assert stale_policy_statements(LK, "c", deployed) == ["DROP POLICY portal_claims_member_mask ON SCHEMA `c`.`larkspur_base`"]
