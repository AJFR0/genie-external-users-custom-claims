# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Create the Genie Agent
# MAGIC The agent sees **only** the portal views. Settings that matter for isolation:
# MAGIC
# MAGIC * **Prompt matching is off** on every claim-keyed view. It samples column values with the author's permissions
# MAGIC   and shares them with all users. It stays on for public reference views.
# MAGIC * Queries **run as the caller** (the default), so every query carries the user's claim.
# MAGIC * The portal service principal gets **Can Run**. Keep **Can Manage** to a small admin group: managers can read
# MAGIC   every conversation and its stored results.
# MAGIC * Instructions tell Genie that the data is already the user's data, and how to answer about other people.
# MAGIC
# MAGIC Genie rejects tables that don't exist yet, which is why this is a job step after the views are created.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

from claims_kit.genie_space import build_serialized_space, grant_can_run, space_title, upsert_space

spec = ex.load_yaml("genie.yml")


def physical(view):
    logical, name = view.split(".", 1)
    return ex.schemas[logical], name


def view_columns(view):
    schema, name = physical(view)
    rows = spark.sql(  # noqa: F821
        f"SELECT column_name FROM `{CATALOG}`.information_schema.columns "
        f"WHERE table_schema = '{schema}' AND table_name = '{name}' ORDER BY ordinal_position").collect()
    return [r.column_name for r in rows]


table_ids = {t["view"]: f"{CATALOG}.{physical(t['view'])[0]}.{physical(t['view'])[1]}" for t in spec["tables"]}
columns = {t["view"]: view_columns(t["view"]) for t in spec["tables"]}
serialized = build_serialized_space(spec, table_ids=table_ids, columns=columns)
space_id, action = upsert_space(w.api_client.do, title=space_title(spec, CATALOG), description=spec["description"],
                                warehouse_id=WAREHOUSE_ID, parent_path=f"/Users/{w.current_user.me().user_name}",
                                serialized_space=serialized)
grant_can_run(w.api_client.do, space_id, portal_sp())
dbutils.jobs.taskValues.set(key="genie_space_id", value=space_id)  # noqa: F821
print(f"Genie Agent {action}: {space_id}. Put it in your .env as {EXAMPLE.upper()}_GENIE_SPACE_ID for the local app.")
