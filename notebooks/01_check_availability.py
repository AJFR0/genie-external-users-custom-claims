# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Check that custom identity claims work here
# MAGIC Custom identity claims are announced on the Databricks *What's coming?* page. Nothing needs to be toggled on.
# MAGIC This step proves it end to end before anything is deployed:
# MAGIC
# MAGIC 1. `DESCRIBE FUNCTION current_oauth_custom_identity_claim`: the SQL function resolves.
# MAGIC 2. `SELECT current_oauth_custom_identity_claim()` from **this** session (no claim): returns `NULL` or raises
# MAGIC    `OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED`, depending on the workspace's current release. That decides how
# MAGIC    step 04 creates the claim-keyed views.
# MAGIC 3. The portal service principal requests a token with `custom_claim=availability-probe`.
# MAGIC 4. That token runs `SELECT current_oauth_custom_identity_claim(), session_user()` through the Statement API and
# MAGIC    must get the claim and its own application id back.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

from claims_kit.availability import run_availability
from claims_kit.tokens import mint_claim_token

report = run_availability(
    admin_scalar=lambda q: spark.sql(q).collect()[0][0],  # noqa: F821
    admin_any=lambda q: spark.sql(q).collect(),  # noqa: F821
    mint=lambda claim: mint_claim_token(HOST, *sp_credentials(), claim),
    sp_runner_for=lambda claim: sp_runner(claim),
)
print("\n".join(report.lines()))
dbutils.jobs.taskValues.set(key="deploy_mode", value=report.deploy_mode)  # noqa: F821
if not report.ready:
    raise RuntimeError("Custom identity claims are not usable in this workspace yet. See the lines above.")
