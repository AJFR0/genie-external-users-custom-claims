from claims_kit.config import load_example
from claims_kit.policies import (DEFAULT_DENY, coverage_problems, coverage_queries, default_deny_sql, drop_statements,
                                 policy_name, policy_sql, policy_statements, tag_statements)
from claims_kit.tags import load_tag_set

NW = load_example("northwind")
GOV = load_tag_set("governed")
GROUP = NW.portal_group


def _rp(ex, table):
    return next(r for r in ex.row_policies if r.table == table)


def test_tag_statements_tag_each_table_and_policy_column():
    stmts = tag_statements(NW, "c", GOV)
    assert "ALTER TABLE `c`.`northwind_base`.`account_balances` SET TAGS ('portal_grain' = 'accounts')" in stmts
    assert ("ALTER TABLE `c`.`northwind_base`.`account_balances` ALTER COLUMN `plan_id` "
            "SET TAGS ('portal_key' = 'tenant')") in stmts
    assert "ALTER TABLE `c`.`northwind_base`.`funds` SET TAGS ('portal_grain' = 'reference')" in stmts


def test_policy_sql_binds_columns_by_tag_in_argument_order():
    sql = policy_sql(NW, "c", GOV, _rp(NW, "base.account_balances"), GROUP)
    assert sql.startswith("CREATE OR REPLACE POLICY portal_accounts_rows ON SCHEMA `c`.`northwind_base`")
    assert "ROW FILTER `c`.`northwind_governance`.`rf_accounts`" in sql
    assert f"TO `{GROUP}`" in sql
    assert "FOR TABLES WHEN has_tag_value('portal_grain', 'accounts')" in sql
    assert ("MATCH COLUMNS has_tag_value('portal_key', 'member') AS member, "
            "has_tag_value('portal_key', 'tenant') AS tenant") in sql
    assert sql.rstrip().endswith("USING COLUMNS (member, tenant)")


def test_reference_tables_get_tags_but_no_policy():
    stmts = policy_statements(NW, "c", GOV, GROUP)
    assert not any("portal_reference_rows" in s for s in stmts)
    assert sum(s.startswith("CREATE OR REPLACE POLICY portal_") and "_rows " in s for s in stmts) == 4


def test_default_deny_covers_the_base_schema_only():
    deny = [s for s in policy_statements(NW, "c", GOV, GROUP) if DEFAULT_DENY in s]
    assert len(deny) == 1
    assert "ON SCHEMA `c`.`northwind_base`" in deny[0]
    assert "FOR TABLES WHEN NOT (has_tag('portal_grain'))" in deny[0]
    assert "ROW FILTER `c`.`northwind_governance`.`rf_deny`" in deny[0]


def test_stand_in_default_deny_lists_every_grain_key():
    sql = default_deny_sql(NW, "c", load_tag_set("stand_in"), "base", GROUP)
    assert sql.count("has_tag('class.") == 9


def test_drop_statements_name_every_policy_without_if_exists():
    stmts = drop_statements(NW, "c")
    assert f"DROP POLICY {policy_name(_rp(NW, 'base.account_balances'))} ON SCHEMA `c`.`northwind_base`" in stmts
    assert len(stmts) == 5 and sum(DEFAULT_DENY in s for s in stmts) == 1
    assert not any("IF EXISTS" in s for s in stmts)


def test_coverage_queries_read_the_base_schema():
    table_q, column_q = coverage_queries(NW, "c")
    assert "`c`.information_schema.table_tags" in table_q and "IN ('northwind_base')" in table_q
    assert "`c`.information_schema.column_tags" in column_q and "column_name" in column_q


def _tags_ok(ex, tags):
    trows, crows = [], []
    for rp in ex.row_policies:
        logical, table = rp.table.split(".", 1)
        g = tags.grain(rp.grain)
        trows.append((ex.schemas[logical], table, g.key, g.value or ""))
        for col, key in rp.columns:
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
    crows = [r for r in crows if not (r[1] == "account_balances" and r[2] == "plan_id")]
    problems = coverage_problems(NW, GOV, trows, crows)
    assert any("contributions" in p and "grain" in p for p in problems)
    assert any("account_balances.plan_id" in p for p in problems)


def test_coverage_flags_ambiguous_key_column():
    trows, crows = _tags_ok(NW, GOV)
    crows.append(("northwind_base", "account_balances", "fund_id", "portal_key", "member"))
    assert any("ambiguous" in p and "account_balances" in p for p in coverage_problems(NW, GOV, trows, crows))
