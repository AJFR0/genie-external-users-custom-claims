# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Entitlements: per user and per role
# MAGIC * `portal_user_grants` holds **per-user** rows: which user, in which role, over which scope, for which dates.
# MAGIC   Onboarding a user is an insert. Revoking is a delete or an expiry date. A user with two roles has two rows.
# MAGIC * `role_policies` holds **per-role** rules: what each role may see. One update changes every user with that role.
# MAGIC
# MAGIC CHECK constraints reject malformed claims and unknown roles, so a bad row can't silently match nothing.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

values = ex.template_values(CATALOG, portal_sp(), VIEW_OWNER)
run_admin_script(ex.read_sql("governance", values))
run_admin_script(ex.read_sql("seed_entitlements", values))
display(spark.table(f"`{CATALOG}`.`{ex.schemas['governance']}`.`portal_user_grants`"))  # noqa: F821
display(spark.table(f"`{CATALOG}`.`{ex.schemas['governance']}`.`role_policies`"))  # noqa: F821
