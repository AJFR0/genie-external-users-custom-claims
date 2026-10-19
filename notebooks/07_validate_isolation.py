# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Prove the isolation
# MAGIC Mints real tokens for every persona and checks each security layer:
# MAGIC
# MAGIC | Layer | What is proved |
# MAGIC |---|---|
# MAGIC | Unity Catalog grants | the portal service principal can't read base or governance objects, change entitlements or run DDL; another application's service principal can't read these views |
# MAGIC | Service principal binding | even with a mistaken grant, a view answers only for its own application |
# MAGIC | Claim → entitlements | each persona sees exactly the rows its grants allow; forged and malformed claims see nothing |
# MAGIC | Role policies | masking and other role rules hold |
# MAGIC | Signed token | edited, unsigned and corrupted tokens are rejected |
# MAGIC | Genie | answers contain the persona's own numbers and nobody else's |
# MAGIC
# MAGIC Results are appended to `<governance schema>.validation_runs`. The task fails if any check fails.
# MAGIC "Documented" rows describe platform behaviors your backend must handle; they never fail the run.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

import uuid
from datetime import datetime, timezone

from claims_kit.validate import SuiteContext, failures, results_as_dicts, run_suite, summarize

other = "larkspur" if EXAMPLE == "northwind" else "northwind"
try:
    other_provider = sp_provider(other)
    other_provider.token_for(f"{load_example(other).claim_prefix}probe")
except Exception as exc:  # the other example may not be bootstrapped
    print(f"cross-application checks skipped: {exc}")
    other_provider = None

space_id = dbutils.jobs.taskValues.get(taskKey="genie_agent", key="genie_space_id", default="", debugValue="")  # noqa: F821
ctx = SuiteContext(example=ex, catalog=CATALOG, host=HOST, warehouse_id=WAREHOUSE_ID, provider=sp_provider(), admin=admin_runner(),
                   other_provider=other_provider, genie_space_id=space_id or None,
                   include_genie=param("include_genie", "true") == "true")
results = run_suite(ctx)
print(summarize(results))

# COMMAND ----------

run_id, run_at = str(uuid.uuid4()), datetime.now(timezone.utc)
rows = [{"run_id": run_id, "run_at": run_at, "example": EXAMPLE, **r} for r in results_as_dicts(results)]
schema = ("run_id STRING, run_at TIMESTAMP, example STRING, case_id STRING, category STRING, persona STRING, passed BOOLEAN, "
          "expected STRING, observed STRING, statement_id STRING")
spark.createDataFrame(rows, schema=schema).write.mode("append").saveAsTable(  # noqa: F821
    f"`{CATALOG}`.`{ex.schemas['governance']}`.`validation_runs`")
failed = failures(results)
if failed:
    raise AssertionError(f"{len(failed)} isolation checks failed: {[r.case_id for r in failed]}")
