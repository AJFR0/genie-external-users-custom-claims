# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Create the schemas and the synthetic base data
# MAGIC Three schemas per example: **base** (pipelines and internal users), **governance** (entitlements and the policy
# MAGIC view) and **portal** (the only schema the portal service principal can read). The data is synthetic and
# MAGIC deterministic: the same rows on every deploy, so the demo runbook can list exact expected answers.
# MAGIC
# MAGIC The catalog comes from the `catalog` parameter. If it does not exist and `create_catalog` is `true`, this step
# MAGIC creates it. If you can't create catalogs, point the bundle at one you can use:
# MAGIC `--var catalog=<existing catalog> --var create_catalog=false`.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

import importlib

from databricks.sdk.errors import NotFound


def catalog_exists(name):
    try:
        w.catalogs.get(name)
        return True
    except NotFound:
        return False


if not catalog_exists(CATALOG):
    hint = f"Rerun with --var catalog=<a catalog you can use> --var create_catalog=false"
    if param("create_catalog", "true") != "true":
        raise RuntimeError(f"Catalog {CATALOG} does not exist and create_catalog is false. {hint}")
    try:
        admin_sql(f"CREATE CATALOG IF NOT EXISTS `{CATALOG}`")
    except Exception as exc:
        raise RuntimeError(f"Could not create catalog {CATALOG} (this needs the CREATE CATALOG privilege). {hint}") from exc
values = ex.template_values(CATALOG, portal_sp(), VIEW_OWNER)
run_admin_script(ex.read_sql("schemas", values))
run_admin_script(ex.read_sql("base_tables", values))

# COMMAND ----------

data = importlib.import_module(f"examples.{EXAMPLE}.generate").generate()
for table, rows in data.items():
    target = f"`{CATALOG}`.`{ex.schemas['base']}`.`{table}`"
    schema = spark.table(target).schema  # noqa: F821
    columns = [f.name for f in schema.fields]
    spark.createDataFrame([tuple(r[c] for c in columns) for r in rows], schema=schema).write.insertInto(target)  # noqa: F821
    print(f"{table}: {len(rows)} rows")
