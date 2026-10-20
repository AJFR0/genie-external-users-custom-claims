from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _jobs():
    for f in sorted((ROOT / "resources").glob("*.yml")):
        for key, job in yaml.safe_load(f.read_text())["resources"]["jobs"].items():
            yield f, key, job


def _job(key):
    return next(job for _, k, job in _jobs() if k == key)


def test_every_notebook_path_exists():
    for f, key, job in _jobs():
        for t in job["tasks"]:
            assert (f.parent / t["notebook_task"]["notebook_path"]).resolve().exists(), f"{key}.{t['task_key']}"


def test_deploy_jobs_run_row_policies_after_claim_views_and_before_grants():
    for key in ("northwind_deploy", "larkspur_deploy"):
        tasks = {t["task_key"]: t for t in _job(key)["tasks"]}
        assert tasks["row_policies"]["depends_on"] == [{"task_key": "claim_views"}]
        assert tasks["runtime_grants"]["depends_on"] == [{"task_key": "row_policies"}]
        assert tasks["row_policies"]["notebook_task"]["notebook_path"].endswith("05_row_policies.py")
        assert {"enforcement", "tag_set"} <= {p["name"] for p in _job(key)["parameters"]}


def test_bootstrap_takes_the_tag_set():
    assert "tag_set" in {p["name"] for p in _job("bootstrap")["parameters"]}


def test_bundle_variables_default_to_layered_and_governed():
    v = yaml.safe_load((ROOT / "databricks.yml").read_text())["variables"]
    assert v["enforcement"]["default"] == "layered" and v["tag_set"]["default"] == "governed"


def test_row_policies_notebook_exits_in_views_mode_and_checks_coverage():
    nb = (ROOT / "notebooks" / "05_row_policies.py").read_text()
    assert 'ENFORCEMENT == "views"' in nb and "remove_row_policies" in nb
    assert "require_governed_tags" in nb and "coverage_problems" in nb


def test_common_reads_enforcement_and_tag_set():
    common = (ROOT / "notebooks" / "_common.py").read_text()
    assert 'param("enforcement", "layered")' in common and 'param("tag_set", "governed")' in common
