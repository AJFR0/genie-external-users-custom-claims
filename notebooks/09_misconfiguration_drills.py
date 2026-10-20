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
# MAGIC | D6 | A masked column sits behind such a view, read by a persona whose role masks it | No mask policy: raw values come back |
# MAGIC
# MAGIC Each drill restores the original state and verifies every layer (portal view, policy reach, tags, deployed
# MAGIC policies) before the next one runs; the drills stop if a restore can't be verified, and don't start on a broken
# MAGIC deployment. Run them on a test deployment, never on one serving real users.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

from claims_kit.drills import patient, run_example, summarize
from claims_kit.personas import load_personas
from claims_kit.tags import load_tag_set

if ENFORCEMENT != "layered":
    dbutils.notebook.exit("drills need enforcement=layered")  # noqa: F821

personas = {p.id: p for p in load_personas(ex)}
other = load_example("larkspur" if EXAMPLE == "northwind" else "northwind").portal_group
admin = admin_runner()
results, baselines = run_example(
    ex, CATALOG, load_tag_set(TAG_SET), admin=admin.execute, admin_rows=lambda q: [tuple(r) for r in admin.execute(q).rows],
    count_as=lambda pid: patient(lambda sql: int(sp_runner(personas[pid].claim).execute(sql).scalar())), other_group=other)
for persona, b in baselines.items():
    print(f"baseline for {persona}: own {b['own']}, reach {b['reach']}, total {b['total']}")
print(summarize(results))
if any(r.passed is False for r in results):
    raise RuntimeError("a drill leaked: see the table above")
