# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Runtime grants: the portal service principal reads portal views, nothing else
# MAGIC `USE CATALOG`, `USE SCHEMA` on the portal schema, and `SELECT` on each portal view. No grants on the base or
# MAGIC governance schemas: views read those with their owner's rights. The isolation suite (step 07) proves it.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

from claims_kit.deploy import apply_runtime_grants

print("\n".join(apply_runtime_grants(ex, catalog=CATALOG, portal_sp=portal_sp(), view_owner=VIEW_OWNER, admin_sql=admin_sql)))
for logical in ("base", "governance", "portal"):
    display(spark.sql(f"SHOW GRANTS `{portal_sp()}` ON SCHEMA `{CATALOG}`.`{ex.schemas[logical]}`"))  # noqa: F821
