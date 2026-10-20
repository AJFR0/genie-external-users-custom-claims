import json

import pytest

from claims_kit.config import load_example
from claims_kit.drills import Drill, build_drills, measure_baseline, patient, run_drills
from claims_kit.sql import StatementError
from claims_kit.tags import load_tag_set

NW = load_example("northwind")
TAGS = load_tag_set("governed")


def test_five_drills_with_their_mistakes():
    drills = build_drills(NW, "c", TAGS, NW.portal_group, "other-group")
    assert [d.id for d in drills] == ["D1", "D2", "D3", "D4", "D5", "D6"]
    d1, d2, d3, d4, d5, _ = drills
    assert "ALTER TABLE `c`.`northwind_base`.`account_balances` ALTER COLUMN `participant_id` UNSET TAGS ('portal_key')" in d1.setup
    assert ("ALTER TABLE `c`.`northwind_base`.`account_balances` ALTER COLUMN `participant_id` "
            "SET TAGS ('portal_key' = 'member')") in d1.restore
    assert d1.layered_sql == "SELECT count(*) FROM `c`.`northwind_portal`.`my_accounts`"
    assert d1.single_sql == "SELECT count(*) FROM `c`.`northwind_portal`.`zz_drill_plain`"
    assert any("TO `other-group`" in s for s in d2.setup) and any(f"TO `{NW.portal_group}`" in s for s in d2.restore)
    assert d3.break_layer == ("DROP POLICY portal_accounts_rows ON SCHEMA `c`.`northwind_base`",)
    assert d4.break_layer == ("DROP POLICY portal_default_deny ON SCHEMA `c`.`northwind_base`",)
    assert any(s.startswith("CREATE OR REPLACE TABLE `c`.`northwind_base`.`zz_drill_new` AS SELECT") for s in d4.setup)
    assert any(s.startswith("GRANT SELECT ON TABLE `c`.`northwind_base`.`account_balances`") for s in d5.setup)
    assert any(s.startswith("REVOKE SELECT ON TABLE `c`.`northwind_base`.`account_balances`") for s in d5.restore)
    assert [d.expect for d in drills] == ["own", "own", "reach", "zero", "reach", "zero"]


class Ops:
    def __init__(self, counts, raise_on=None, fail_on=None):
        self.admin_log, self.counts, self.raise_on, self.fail_on = [], counts, raise_on, fail_on

    def admin(self, sql):
        self.admin_log.append(sql)
        if self.fail_on and sql.startswith(self.fail_on):
            raise RuntimeError("restore statement failed")

    def sp_count(self, sql):
        if self.raise_on and self.raise_on in sql:
            raise RuntimeError("token error")
        return self.counts[sql]


def _drill(expect="own"):
    return Drill("D1", "untag", setup=("SETUP",), layered_sql="LAYERED", break_layer=("BREAK",), single_sql="SINGLE",
                 restore=("RESTORE",), expect=expect)


BASE = {"own": 2, "reach": 2, "total": 50}


def _run(ops, drills, verify=None):
    def default_verify():
        own = ops.sp_count("VERIFY")
        return [] if own == BASE["own"] else [f"portal view returns {own}"]
    return run_drills(drills, admin=ops.admin, sp_count=ops.sp_count, baseline=BASE, verify=verify or default_verify)


def test_layered_count_matching_expectation_passes_and_single_layer_is_evidence():
    ops = Ops({"LAYERED": 2, "SINGLE": 50, "VERIFY": 2})
    [r] = _run(ops, [_drill()])
    assert (r.passed, r.layered_rows, r.single_layer_rows, r.restored) == (True, 2, 50, True)
    assert ops.admin_log == ["SETUP", "BREAK", "RESTORE"]


def test_single_layer_that_did_not_leak_is_inconclusive():
    [r] = _run(Ops({"LAYERED": 2, "SINGLE": 2, "VERIFY": 2}), [_drill()])
    assert r.passed is None and "did not remove" in r.observed


def test_layered_leak_fails():
    [r] = _run(Ops({"LAYERED": 50, "SINGLE": 50, "VERIFY": 2}), [_drill()])
    assert r.passed is False


def test_zero_expectation_for_default_deny():
    [r] = _run(Ops({"LAYERED": 0, "SINGLE": 50, "VERIFY": 2}), [_drill("zero")])
    assert r.passed is True


def test_restore_runs_when_measure_raises():
    ops = Ops({"VERIFY": 2}, raise_on="LAYERED")
    [r] = _run(ops, [_drill()])
    assert ops.admin_log[-1] == "RESTORE" and r.passed is None and r.restored is True


def test_failed_restore_stops_the_drills():
    ops = Ops({"LAYERED": 2, "SINGLE": 50, "VERIFY": 2}, fail_on="RESTORE")
    with pytest.raises(RuntimeError, match="restore failed for D1"):
        _run(ops, [_drill(), _drill()])
    assert ops.admin_log.count("SETUP") == 1


def test_restore_that_does_not_bring_back_the_baseline_stops_the_drills():
    # a portal view that already disagrees with the baseline is caught before any drill runs
    with pytest.raises(RuntimeError, match="precondition"):
        _run(Ops({"LAYERED": 2, "SINGLE": 50, "VERIFY": 7}), [_drill()])


def test_a_policy_layer_left_broken_by_a_restore_stops_the_drills():
    """Review #4: verification checks the policy layer too, not only the portal view the drills never break."""
    calls = []

    def verify():
        calls.append(1)
        return [] if len(calls) == 1 else ["reach through a plain view is 50, expected 2"]

    with pytest.raises(RuntimeError, match="reach through a plain view"):
        _run(Ops({"LAYERED": 2, "SINGLE": 50, "VERIFY": 2}), [_drill()], verify=verify)


def test_drills_refuse_to_start_on_a_broken_deployment():
    ops = Ops({"VERIFY": 2})
    with pytest.raises(RuntimeError, match="precondition"):
        _run(ops, [_drill()], verify=lambda: ["accounts: grain tag missing"])
    assert ops.admin_log == []


def test_mask_drill_counts_raw_values_through_an_unfiltered_view():
    drills = build_drills(NW, "c", TAGS, NW.portal_group, "other-group")
    d6 = next(d for d in drills if d.id == "D6")
    assert d6.expect == "zero" and "date_of_birth IS NOT NULL" in d6.layered_sql
    assert d6.break_layer == ("DROP POLICY portal_roster_birth_date_mask ON SCHEMA `c`.`northwind_base`",)


def test_baseline_drops_its_plain_view_even_when_counting_fails():
    log = []

    def sp_count(sql):
        if "zz_drill_plain" in sql:
            raise RuntimeError("denied")
        return 3

    with pytest.raises(RuntimeError):
        measure_baseline(NW, "c", NW.portal_group, admin=log.append, sp_count=sp_count, admin_count=lambda sql: 99)
    assert log[-1] == "DROP VIEW IF EXISTS `c`.`northwind_portal`.`zz_drill_plain`"


def test_patient_retries_permission_errors_only():
    calls, slept = [], []

    def fn(sql):
        calls.append(sql)
        if len(calls) < 3:
            raise StatementError("[INSUFFICIENT_PERMISSIONS] not yet")
        return 4

    assert patient(fn, timeout_s=60, sleep=slept.append)("Q") == 4 and slept == [10, 10]
    with pytest.raises(StatementError):
        patient(lambda sql: (_ for _ in ()).throw(StatementError("[DIVIDE_BY_ZERO] x")), timeout_s=60, sleep=slept.append)("Q")


def test_drill_evidence_is_scrubbed(tmp_path):
    from claims_kit.drills import DrillResult
    from claims_kit.evidence import write_drill_evidence

    class Ctx:
        example, catalog, host, warehouse_id = NW, "secret_catalog", "https://h.example", "wh-1"

        class provider:
            client_id = "app-1"
        other_provider = None

    r = DrillResult("D1", "untag `secret_catalog`.x", "own", 2, 50, 2, 50, True, True, "ok at https://h.example")
    path = write_drill_evidence(Ctx, [r], tmp_path)
    text = path.read_text()
    assert "secret_catalog" not in text and "h.example" not in text
    assert json.loads(text)["results"][0]["drill_id"] == "D1"



def test_mask_drill_falls_back_to_the_row_policy_when_a_table_has_no_mask():
    lk = load_example("larkspur")
    d6 = next(d for d in build_drills(lk, "c", TAGS, lk.portal_group, "other-group") if d.id == "D6")
    assert d6.persona == "priya" and "member_id LIKE 'M-%'" in d6.layered_sql
    assert d6.break_layer == ("DROP POLICY portal_claims_rows ON SCHEMA `c`.`larkspur_base`",)
