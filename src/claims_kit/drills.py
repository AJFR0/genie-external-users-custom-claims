"""Misconfiguration drills (layered mode): make one mistake at a time and measure what reaches a portal user.

Each drill measures twice. First with the mistake in place and every other layer intact, which must still return only
what the persona may see. Then with one layer alone, which shows what a single-layer design would have returned.
Every drill restores the original state, and the drills stop if a restore can't be verified.

  D1  a key column loses its tag                     ABAC alone: a plain view over the table
  D2  the row policy names another group             ABAC alone: a plain view over the table
  D3  a view without the claim filter is granted     views alone: the same view with the table's policy dropped
  D4  a new untagged table sits behind such a view   no default-deny: the same view with default-deny dropped
  D5  a base table is granted to the portal          views alone: the same grant with the table's policy dropped

Run them against a test deployment: python -m claims_kit.drills --example northwind [--evidence docs/evidence]
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Example
from .policies import DEFAULT_DENY, default_deny_sql, policy_name, policy_sql
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
    ]


def measure_baseline(ex: Example, catalog: str, group: str, *, admin, sp_count, admin_count) -> dict:
    """What the persona sees through the portal view (own), what the row policy alone admits (reach), and the total."""
    plan = ex.drills
    plain = ex.fq(catalog, PLAIN_VIEW)
    own = sp_count(_count(ex.fq(catalog, f"portal.{plan['view']}")))
    try:
        admin(f"CREATE OR REPLACE VIEW {plain} AS SELECT * FROM {ex.fq(catalog, plan['table'])}")
        admin(f"GRANT SELECT ON VIEW {plain} TO `{group}`")
        reach = sp_count(_count(plain))
    finally:
        admin(f"DROP VIEW IF EXISTS {plain}")
    return {"own": own, "reach": reach, "total": admin_count(_count(ex.fq(catalog, plan["table"])))}


def run_drills(drills, *, admin, sp_count, baseline: dict, verify_sql: str) -> list[DrillResult]:
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
            verified = None
            if not errors:
                try:
                    verified = sp_count(verify_sql)
                except Exception as exc:
                    errors.append(f"verify: {str(exc)[:120]}")
            if errors or verified != baseline["own"]:
                detail = errors or [f"portal view returns {verified} rows, expected {baseline['own']}"]
                raise RuntimeError(f"restore failed for {d.id}; stopping the drills: {detail}")
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


def main(argv: list[str] | None = None) -> int:
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
    persona = next(p for p in load_personas(ex) if p.id == ex.drills["persona"])
    other = "larkspur" if ex.name == "northwind" else "northwind"
    from .config import load_example
    count = patient(lambda sql: int(ctx.sp_runner(persona.claim).execute(sql).scalar()))
    admin = ctx.admin.execute
    baseline = measure_baseline(ex, ctx.catalog, ex.portal_group, admin=admin, sp_count=count,
                                admin_count=lambda sql: int(ctx.admin.execute(sql).scalar()))
    drills = build_drills(ex, ctx.catalog, load_tag_set(env.tag_set), ex.portal_group, load_example(other).portal_group)
    results = run_drills(drills, admin=admin, sp_count=count, baseline=baseline,
                         verify_sql=_count(ex.fq(ctx.catalog, f"portal.{ex.drills['view']}")))
    print(f"baseline for {persona.id}: own {baseline['own']}, reach {baseline['reach']}, total {baseline['total']}")
    print(summarize(results))
    if args.evidence:
        from .evidence import write_drill_evidence
        write_drill_evidence(ctx, results, args.evidence, baseline=baseline, persona=persona.id)
    return 1 if any(r.passed is False for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
