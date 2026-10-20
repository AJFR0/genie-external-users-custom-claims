"""Misconfiguration drills (layered mode): make one mistake at a time and measure what reaches a portal user.

Each drill measures twice. First with the mistake in place and every other layer intact, which must still return only
what the persona may see. Then with one layer alone, which shows what a single-layer design would have returned.
Every drill restores the original state, and the drills stop if a restore can't be verified.

  D1  a key column loses its tag                     ABAC alone: a plain view over the table
  D2  the row policy names another group             ABAC alone: a plain view over the table
  D3  a view without the claim filter is granted     views alone: the same view with the table's policy dropped
  D4  a new untagged table sits behind such a view   no default-deny: the same view with default-deny dropped
  D5  a base table is granted to the portal          views alone: the same grant with the table's policy dropped
  D6  a masked column sits behind an unfiltered view  no mask policy: raw values come back (as a masked persona)

Run them against a test deployment: python -m claims_kit.drills --example northwind [--evidence docs/evidence]
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Example
from .policies import (DEFAULT_DENY, coverage_problems, coverage_queries, default_deny_sql, mask_policy_name, mask_sql,
                       policy_name, policy_problems, policy_sql)
from .sql import StatementError
from .tags import TagSet, load_tag_set

PLAIN_VIEW = "portal.zz_drill_plain"
NEW_TABLE = "base.zz_drill_new"
NEW_VIEW = "portal.zz_drill_new_view"


@dataclass(frozen=True)
class Drill:
    id: str
    mistake: str
    setup: tuple
    layered_sql: str
    break_layer: tuple
    single_sql: str
    restore: tuple
    expect: str  # own | reach | zero
    persona: str | None = None  # None: the drills persona; set for the mask drill


@dataclass
class DrillResult:
    drill_id: str
    mistake: str
    expect: str
    layered_rows: int | None
    single_layer_rows: int | None
    expected_rows: int | None
    total_rows: int | None
    restored: bool
    passed: bool | None
    observed: str


def _count(fq: str) -> str:
    return f"SELECT count(*) FROM {fq}"


def build_drills(ex: Example, catalog: str, tags: TagSet, group: str, other_group: str) -> list[Drill]:
    plan = ex.drills
    rp = next(r for r in ex.row_policies if r.table == plan["table"])
    key = tags.key(dict(rp.columns)[plan["key_column"]])
    table, view = ex.fq(catalog, rp.table), ex.fq(catalog, f"portal.{plan['view']}")
    plain, new_table, new_view = ex.fq(catalog, PLAIN_VIEW), ex.fq(catalog, NEW_TABLE), ex.fq(catalog, NEW_VIEW)
    base = f"`{catalog}`.`{ex.schemas['base']}`"
    g = f"`{group}`"
    column = f"ALTER TABLE {table} ALTER COLUMN `{plan['key_column']}`"
    make_plain = (f"CREATE OR REPLACE VIEW {plain} AS SELECT * FROM {table}", f"GRANT SELECT ON VIEW {plain} TO {g}")
    drop_plain = f"DROP VIEW IF EXISTS {plain}"
    drop_policy = f"DROP POLICY {policy_name(rp)} ON SCHEMA {base}"
    restore_policy = policy_sql(ex, catalog, tags, rp, group)
    return [
        Drill("D1", f"tag removed from the key column {rp.table}.{plan['key_column']}",
              (f"{column} UNSET TAGS ('{key.key}')",) + make_plain, _count(view), (), _count(plain),
              (f"{column} SET TAGS ({key.assignment()})", drop_plain), "own"),
        Drill("D2", "the row policy names another application's group",
              (policy_sql(ex, catalog, tags, rp, other_group),) + make_plain, _count(view), (), _count(plain),
              (restore_policy, drop_plain), "own"),
        Drill("D3", "a view without the claim filter is granted to the portal",
              make_plain, _count(plain), (drop_policy,), _count(plain), (restore_policy, drop_plain), "reach"),
        Drill("D4", "a new untagged table is exposed through a view without the claim filter",
              (f"CREATE OR REPLACE TABLE {new_table} AS SELECT * FROM {table}",
               f"CREATE OR REPLACE VIEW {new_view} AS SELECT * FROM {new_table}", f"GRANT SELECT ON VIEW {new_view} TO {g}"),
              _count(new_view), (f"DROP POLICY {DEFAULT_DENY} ON SCHEMA {base}",), _count(new_view),
              (default_deny_sql(ex, catalog, tags, "base", group), f"DROP VIEW IF EXISTS {new_view}",
               f"DROP TABLE IF EXISTS {new_table}"), "zero"),
        Drill("D5", f"the base table {rp.table} is granted to the portal directly",
              (f"GRANT USE SCHEMA ON SCHEMA {base} TO {g}", f"GRANT SELECT ON TABLE {table} TO {g}"),
              _count(table), (drop_policy,), _count(table),
              (restore_policy, f"REVOKE SELECT ON TABLE {table} FROM {g}", f"REVOKE USE SCHEMA ON SCHEMA {base} FROM {g}"),
              "reach"),
    ] + _mask_drill(ex, catalog, tags, group, plain, drop_plain, base)


def _mask_drill(ex, catalog, tags, group, plain, drop_plain, base) -> list:
    cfg = (ex.drills or {}).get("mask")
    if not cfg:
        return []
    m = next(x for x in ex.column_masks if x.table == cfg["table"])
    table = ex.fq(catalog, m.table)
    raw = f"SELECT count(*) FROM {plain} WHERE {cfg['raw_where']}"
    return [Drill("D6", f"a view without the claim filter exposes the masked column {m.table}.{m.column[0]}",
                  (f"CREATE OR REPLACE VIEW {plain} AS SELECT * FROM {table}", f"GRANT SELECT ON VIEW {plain} TO `{group}`"),
                  raw, (f"DROP POLICY {mask_policy_name(m)} ON SCHEMA {base}",), raw,
                  (mask_sql(ex, catalog, tags, m, group), drop_plain), "zero", persona=cfg["persona"])]


def measure_baseline(ex: Example, catalog: str, group: str, *, admin, sp_count, admin_count, view: str | None = None,
                     table: str | None = None) -> dict:
    """What the persona sees through the portal view (own), what the row policy alone admits (reach), and the total."""
    view, table = view or ex.drills["view"], table or ex.drills["table"]
    plain = ex.fq(catalog, PLAIN_VIEW)
    own = sp_count(_count(ex.fq(catalog, f"portal.{view}")))
    try:
        admin(f"CREATE OR REPLACE VIEW {plain} AS SELECT * FROM {ex.fq(catalog, table)}")
        admin(f"GRANT SELECT ON VIEW {plain} TO `{group}`")
        reach = sp_count(_count(plain))
    finally:
        admin(f"DROP VIEW IF EXISTS {plain}")
    return {"own": own, "reach": reach, "total": admin_count(_count(ex.fq(catalog, table)))}


def run_drills(drills, *, admin, sp_count, baseline: dict, verify) -> list[DrillResult]:
    """`verify()` returns the problems with the deployment (empty when every layer is intact). It runs before the
    first drill and after every restore, and any problem stops the drills."""
    problems = verify()
    if problems:
        raise RuntimeError(f"precondition failed, not running the drills: {problems}")
    results = []
    for d in drills:
        layered = single = None
        note = ""
        try:
            for stmt in d.setup:
                admin(stmt)
            layered = sp_count(d.layered_sql)
            for stmt in d.break_layer:
                admin(stmt)
            single = sp_count(d.single_sql)
        except Exception as exc:
            note = f"inconclusive: measuring failed ({str(exc)[:160]})"
        finally:
            errors = []
            for stmt in d.restore:
                try:
                    admin(stmt)
                except Exception as exc:
                    errors.append(f"{stmt.split(chr(10))[0][:80]}: {str(exc)[:120]}")
            if not errors:
                try:
                    errors += verify()
                except Exception as exc:
                    errors.append(f"verify: {str(exc)[:120]}")
            if errors:
                raise RuntimeError(f"restore failed for {d.id}; stopping the drills: {errors}")
        expected = {"own": baseline["own"], "reach": baseline["reach"], "zero": 0}[d.expect]
        if layered is None:
            passed, observed = None, note
        elif layered != expected:
            passed, observed = False, f"leak: with the mistake in place the portal returned {layered} rows, expected {expected}"
        elif single is None or single <= expected:
            passed, observed = None, f"inconclusive: the mistake did not remove the other layer (one layer alone returned {single})"
        else:
            passed, observed = True, (f"held: {layered} rows with the mistake in place (expected {expected}); "
                                      f"one layer alone returned {single} of {baseline['total']}")
        results.append(DrillResult(d.id, d.mistake, d.expect, layered, single, expected, baseline["total"], True, passed, observed))
    return results


def make_verifier(ex: Example, catalog: str, tags: TagSet, group: str, *, admin, admin_rows, sp_count, baseline: dict,
                  view: str, table: str):
    """Every layer intact: the portal view and the plain-view reach match the baseline, every tag is in place, and every
    policy is deployed. Counting the portal view alone would miss a policy layer that failed to come back."""
    plain = ex.fq(catalog, PLAIN_VIEW)

    def verify() -> list:
        problems = []
        own = sp_count(_count(ex.fq(catalog, f"portal.{view}")))
        if own != baseline["own"]:
            problems.append(f"portal view {view} returns {own} rows, expected {baseline['own']}")
        if "reach" in baseline:
            try:
                admin(f"CREATE OR REPLACE VIEW {plain} AS SELECT * FROM {ex.fq(catalog, table)}")
                admin(f"GRANT SELECT ON VIEW {plain} TO `{group}`")
                reach = sp_count(_count(plain))
            finally:
                admin(f"DROP VIEW IF EXISTS {plain}")
            if reach != baseline["reach"]:
                problems.append(f"reach through a plain view is {reach}, expected {baseline['reach']}")
        table_q, column_q = coverage_queries(ex, catalog)
        problems += coverage_problems(ex, tags, admin_rows(table_q), admin_rows(column_q))
        names = [r[0] for r in admin_rows(f"SHOW POLICIES ON SCHEMA `{catalog}`.`{ex.schemas['base']}`")]
        problems += policy_problems(ex, names, "layered")
        return problems
    return verify


def patient(fn, *, timeout_s: float = 300, sleep=time.sleep):
    """Wrap a count so permission errors are retried: a new grant can take minutes to reach Unity Catalog."""
    def call(sql):
        waited = 0
        while True:
            try:
                return fn(sql)
            except StatementError as e:
                if not e.is_permission_error or waited >= timeout_s:
                    raise
            sleep(10)
            waited += 10
    return call


def summarize(results: list[DrillResult]) -> str:
    lines = [f"{'drill':<5} {'result':<12} {'layered':>8} {'one layer':>10} {'total':>7}  mistake"]
    for r in results:
        tag = {True: "held", False: "LEAK", None: "inconclusive"}[r.passed]
        lines.append(f"{r.drill_id:<5} {tag:<12} {str(r.layered_rows):>8} {str(r.single_layer_rows):>10} {str(r.total_rows):>7}  {r.mistake}")
    return "\n".join(lines)


def results_as_dicts(results: list[DrillResult]) -> list[dict]:
    return [asdict(r) for r in results]


def run_example(ex: Example, catalog: str, tags: TagSet, *, admin, admin_rows, count_as, other_group: str) -> tuple:
    """Run every drill for one example: D1 to D5 as the drills persona, D6 as the mask persona. Returns (results, baselines)."""
    drills = build_drills(ex, catalog, tags, ex.portal_group, other_group)
    plan, mask = ex.drills, (ex.drills or {}).get("mask")
    results, baselines = [], {}
    for persona, view, table, group_drills in ((plan["persona"], plan["view"], plan["table"], [d for d in drills if not d.persona]),
                                               *(((mask["persona"], mask["view"], mask["table"], [d for d in drills if d.persona]),)
                                                 if mask else ())):
        count = count_as(persona)
        baseline = measure_baseline(ex, catalog, ex.portal_group, admin=admin, sp_count=count,
                                    admin_count=lambda sql: int(admin_rows(sql)[0][0]), view=view, table=table)
        verify = make_verifier(ex, catalog, tags, ex.portal_group, admin=admin, admin_rows=admin_rows, sp_count=count,
                               baseline=baseline, view=view, table=table)
        results += run_drills(group_drills, admin=admin, sp_count=count, baseline=baseline, verify=verify)
        baselines[persona] = baseline
    return results, baselines


def main(argv: list[str] | None = None) -> int:
    from .config import load_example
    from .local import LocalEnv, read_env
    from .personas import load_personas
    from .validate import build_local_context

    parser = argparse.ArgumentParser(description="Run the misconfiguration drills against a layered deployment")
    parser.add_argument("--example", required=True, choices=("northwind", "larkspur"))
    parser.add_argument("--evidence", type=Path, help="write scrubbed JSON evidence into this directory")
    args = parser.parse_args(argv)
    env = LocalEnv.from_mapping(read_env())
    if env.enforcement != "layered":
        print("drills need a layered deployment (ENFORCEMENT=layered)")
        return 2
    ctx = build_local_context(args.example, include_genie=False)
    ex = ctx.example
    personas = {p.id: p for p in load_personas(ex)}
    other = load_example("larkspur" if ex.name == "northwind" else "northwind").portal_group

    def count_as(persona_id):
        return patient(lambda sql: int(ctx.sp_runner(personas[persona_id].claim).execute(sql).scalar()))

    results, baselines = run_example(ex, ctx.catalog, load_tag_set(env.tag_set), admin=ctx.admin.execute,
                                     admin_rows=lambda sql: [tuple(r) for r in ctx.admin.execute(sql).rows],
                                     count_as=count_as, other_group=other)
    for persona, b in baselines.items():
        print(f"baseline for {persona}: own {b['own']}, reach {b.get('reach')}, total {b['total']}")
    print(summarize(results))
    if args.evidence:
        from .evidence import write_drill_evidence
        write_drill_evidence(ctx, results, args.evidence, baseline=baselines, persona=", ".join(baselines))
    return 1 if any(r.passed is False for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
