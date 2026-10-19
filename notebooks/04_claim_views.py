# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Create the claim-keyed views
# MAGIC `governance.my_effective_grants` is the only object that reads the claim. The portal views join to it.
# MAGIC
# MAGIC How the views get created depends on what `current_oauth_custom_identity_claim()` does **without** a claim:
# MAGIC
# MAGIC | Workspace behavior | How this step creates the views |
# MAGIC |---|---|
# MAGIC | returns `NULL` | you create them directly |
# MAGIC | raises `OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED` | the portal service principal gets **temporary** rights, creates them from a session whose token carries a claim, you take ownership, and the temporary rights are revoked (even if a statement fails) |
# MAGIC
# MAGIC Either way the views end up owned by `view_owner`, and the portal service principal ends up with no rights
# MAGIC on the base and governance schemas.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

from claims_kit.availability import classify_no_claim
from claims_kit.deploy import DEPLOY_CLAIM, create_public_views, deploy_claim_views

behavior = classify_no_claim(lambda q: spark.sql(q).collect()[0][0])  # noqa: F821
mode = "null" if behavior == "null" else "throws"
print(f"No-claim behavior: {behavior} -> deploy mode: {mode}")
common = dict(catalog=CATALOG, portal_sp=portal_sp(), view_owner=VIEW_OWNER, admin_sql=admin_sql)
log = deploy_claim_views(ex, mode=mode, sp_runner=sp_runner(DEPLOY_CLAIM) if mode == "throws" else None, **common)
log += create_public_views(ex, **common)
print("\n".join(line[:160] for line in log))
