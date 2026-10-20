# Databricks notebook source
# MAGIC %md
# MAGIC # 09 · Misconfiguration drills (layered enforcement)
# MAGIC Make one mistake at a time and measure what reaches a portal user. Each drill measures twice: with the mistake in
# MAGIC place and every other layer intact, which must still return only what the persona may see, and with one layer
# MAGIC alone, which shows what a single-layer design would have returned.
# MAGIC
# MAGIC | Drill | Mistake | One layer alone |
# MAGIC |---|---|---|
# MAGIC | D1 | A key column loses its tag | ABAC alone: a plain view over the table |
# MAGIC | D2 | The row policy names another application's group | ABAC alone: a plain view over the table |
# MAGIC | D3 | A view without the claim filter is granted | Views alone: the same view with the table's policy dropped |
# MAGIC | D4 | A new untagged table sits behind such a view | No default-deny: the same view with default-deny dropped |
# MAGIC | D5 | A base table is granted to the portal directly | Views alone: the same grant with the table's policy dropped |
# MAGIC
# MAGIC Each drill restores the original state and verifies it before the next one runs; the drills stop if a restore
# MAGIC can't be verified. Run them on a test deployment, never on one serving real users.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

from claims_kit.drills import build_drills, measure_baseline, patient, run_drills, summarize
from claims_kit.personas import load_personas
from claims_kit.tags import load_tag_set

if ENFORCEMENT != "layered":
    dbutils.notebook.exit("drills need enforcement=layered")  # noqa: F821

persona = next(p for p in load_personas(ex) if p.id == ex.drills["persona"])
other = load_example("larkspur" if EXAMPLE == "northwind" else "northwind").portal_group
admin = admin_runner().execute
count = patient(lambda sql: int(sp_runner(persona.claim).execute(sql).scalar()))
baseline = measure_baseline(ex, CATALOG, ex.portal_group, admin=admin, sp_count=count,
                            admin_count=lambda sql: int(admin_runner().execute(sql).scalar()))
print(f"baseline for {persona.id}: own {baseline['own']}, reach {baseline['reach']}, total {baseline['total']}")
results = run_drills(build_drills(ex, CATALOG, load_tag_set(TAG_SET), ex.portal_group, other), admin=admin, sp_count=count,
                     baseline=baseline, verify_sql=f"SELECT count(*) FROM {ex.fq(CATALOG, 'portal.' + ex.drills['view'])}")
print(summarize(results))
if any(r.passed is False for r in results):
    raise RuntimeError("a drill leaked: see the table above")
