"""SQL for the row policies (layered enforcement): tags, ABAC row-filter policies and default-deny.

Everything is generated from examples/<name>/example.yml (row_policies) and a tag set, so deploy, the coverage
self-check and the misconfiguration drills all use the same definitions. Policies attach to the base schema only:
governance tables are the policies' inputs, and a schema-level policy would also match the governance views.
"""
from __future__ import annotations

from .config import ColumnMask, Example, RowPolicy
from .tags import TagSet

DEFAULT_DENY = "portal_default_deny"
DENY_SCHEMAS = ("base",)


def policy_name(rp: RowPolicy) -> str:
    return f"portal_{rp.grain}_rows"


def _schema(ex: Example, catalog: str, logical: str) -> str:
    return f"`{catalog}`.`{ex.schemas[logical]}`"


def mask_policy_name(m: ColumnMask) -> str:
    return f"portal_{m.grain}_{m.column[1]}_mask"


def _tagged_columns(ex: Example):
    """(table, grain, [(column, key), ...]) for every protected table, with mask columns merged in."""
    seen: dict = {}
    for rp in ex.row_policies:
        seen.setdefault(rp.table, [rp.grain, []])[1].extend(rp.columns)
    for m in ex.column_masks:
        entry = seen.setdefault(m.table, [m.grain, []])
        entry[1].extend((m.column, *m.using))
    return [(table, grain, list(dict.fromkeys(cols))) for table, (grain, cols) in seen.items()]


def tag_statements(ex: Example, catalog: str, tags: TagSet) -> list[str]:
    out = []
    for table, grain, columns in _tagged_columns(ex):
        fq = ex.fq(catalog, table)
        out.append(f"ALTER TABLE {fq} SET TAGS ({tags.grain(grain).assignment()})")
        out += [f"ALTER TABLE {fq} ALTER COLUMN `{col}` SET TAGS ({tags.key(key).assignment()})" for col, key in columns]
    return out


def policy_sql(ex: Example, catalog: str, tags: TagSet, rp: RowPolicy, group: str) -> str:
    match = ", ".join(f"{tags.key(key).condition()} AS {key}" for _, key in rp.columns)
    using = ", ".join(key for _, key in rp.columns)
    return (f"CREATE OR REPLACE POLICY {policy_name(rp)} ON SCHEMA {_schema(ex, catalog, rp.schema)}\n"
            f"COMMENT 'Portal rows of {rp.table.split('.', 1)[1]} for the signed-in user (layered enforcement)'\n"
            f"ROW FILTER {ex.fq(catalog, 'governance.' + rp.function)}\n"
            f"TO `{group}`\n"
            f"FOR TABLES WHEN {tags.grain(rp.grain).condition()}\n"
            f"MATCH COLUMNS {match}\n"
            f"USING COLUMNS ({using})")


def mask_sql(ex: Example, catalog: str, tags: TagSet, m: ColumnMask, group: str) -> str:
    col, key = m.column
    match = ", ".join(f"{tags.key(k).condition()} AS {k}" for _, k in (m.column, *m.using))
    using = f"\nUSING COLUMNS ({', '.join(k for _, k in m.using)})" if m.using else ""
    return (f"CREATE OR REPLACE POLICY {mask_policy_name(m)} ON SCHEMA {_schema(ex, catalog, m.schema)}\n"
            f"COMMENT 'Portal mask of {m.table.split('.', 1)[1]}.{col} for the signed-in user (layered enforcement)'\n"
            f"COLUMN MASK {ex.fq(catalog, 'governance.' + m.function)}\n"
            f"TO `{group}`\n"
            f"FOR TABLES WHEN {tags.grain(m.grain).condition()}\n"
            f"MATCH COLUMNS {match}\n"
            f"ON COLUMN {key}{using}")


def default_deny_sql(ex: Example, catalog: str, tags: TagSet, schema: str, group: str) -> str:
    return (f"CREATE OR REPLACE POLICY {DEFAULT_DENY} ON SCHEMA {_schema(ex, catalog, schema)}\n"
            f"COMMENT 'Default deny: a table without a portal grain tag returns no rows to the portal'\n"
            f"ROW FILTER {ex.fq(catalog, 'governance.rf_deny')}\n"
            f"TO `{group}`\n"
            f"FOR TABLES WHEN NOT ({tags.any_grain()})")


def policy_statements(ex: Example, catalog: str, tags: TagSet, group: str) -> list[str]:
    filters = [policy_sql(ex, catalog, tags, rp, group) for rp in ex.row_policies if rp.function]
    masks = [mask_sql(ex, catalog, tags, m, group) for m in ex.column_masks]
    return filters + masks + [default_deny_sql(ex, catalog, tags, s, group) for s in DENY_SCHEMAS]


def drop_statements(ex: Example, catalog: str) -> list[str]:
    """DROP POLICY has no IF EXISTS; callers tolerate POLICY_NOT_FOUND."""
    out = [f"DROP POLICY {policy_name(rp)} ON SCHEMA {_schema(ex, catalog, rp.schema)}" for rp in ex.row_policies if rp.function]
    out += [f"DROP POLICY {mask_policy_name(m)} ON SCHEMA {_schema(ex, catalog, m.schema)}" for m in ex.column_masks]
    return out + [f"DROP POLICY {DEFAULT_DENY} ON SCHEMA {_schema(ex, catalog, s)}" for s in DENY_SCHEMAS]


def expected_policy_names(ex: Example) -> list[str]:
    return ([policy_name(rp) for rp in ex.row_policies if rp.function] + [mask_policy_name(m) for m in ex.column_masks]
            + [DEFAULT_DENY])


def stale_policy_statements(ex: Example, catalog: str, deployed_names) -> list[str]:
    """DROP statements for portal policies this version no longer defines (renamed or removed). Others are left alone."""
    expected = set(expected_policy_names(ex))
    return [f"DROP POLICY {n} ON SCHEMA {_schema(ex, catalog, 'base')}" for n in sorted(deployed_names)
            if n.startswith("portal_") and n not in expected]


def policy_problems(ex: Example, deployed_names, enforcement: str) -> list[str]:
    """The deployment decides the enforcement model, not the local configuration."""
    expected, deployed = set(expected_policy_names(ex)), set(deployed_names)
    if enforcement == "layered":
        missing = sorted(expected - deployed)
        return [f"layered enforcement but policies missing on the base schema: {missing}"] if missing else []
    present = sorted(expected & deployed)
    return [f"views enforcement but row policies are still deployed: {present}"] if present else []


def coverage_queries(ex: Example, catalog: str) -> tuple[str, str]:
    schemas = ", ".join(f"'{ex.schemas[s]}'" for s in DENY_SCHEMAS)
    return (f"SELECT schema_name, table_name, tag_name, coalesce(tag_value, '') "
            f"FROM `{catalog}`.information_schema.table_tags WHERE schema_name IN ({schemas})",
            f"SELECT schema_name, table_name, column_name, tag_name, coalesce(tag_value, '') "
            f"FROM `{catalog}`.information_schema.column_tags WHERE schema_name IN ({schemas})")


def coverage_problems(ex: Example, tags: TagSet, table_tag_rows, column_tag_rows) -> list[str]:
    """Every protected table carries its grain, and each policy key tag sits on exactly the intended column."""
    table_tags = {(s, t, k, v or "") for s, t, k, v in table_tag_rows}
    col_tags = [(s, t, c, k, v or "") for s, t, c, k, v in column_tag_rows]
    problems = []
    for full, grain, columns in _tagged_columns(ex):
        logical, table = full.split(".", 1)
        schema, g = ex.schemas[logical], tags.grain(grain)
        if (schema, table, g.key, g.value or "") not in table_tags:
            problems.append(f"{full}: grain tag {g.assignment()} missing")
        for col, key in columns:
            k = tags.key(key)
            hits = sorted(c for s, t, c, kk, vv in col_tags if (s, t, kk, vv) == (schema, table, k.key, k.value or ""))
            if col not in hits:
                problems.append(f"{full}.{col}: key tag {k.assignment()} missing")
            if len(hits) > 1:
                problems.append(f"{full}: key tag {k.assignment()} is ambiguous, on columns {hits}")
    return problems
