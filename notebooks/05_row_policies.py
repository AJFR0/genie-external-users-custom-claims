# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Row policies (layered enforcement)
# MAGIC The claim-keyed views from step 04 decide what the portal can reach. This step adds a second, independent filter
# MAGIC underneath them: an ABAC row-filter policy on every base table those views read.
# MAGIC
# MAGIC | Object | What it does |
# MAGIC |---|---|
# MAGIC | Grain tag on each table | Selects the one row policy that applies to it (`portal_grain`) |
# MAGIC | Key tags on columns | Bind the table's columns to the policy function's arguments (`portal_key`) |
# MAGIC | `rf_*` functions | Admit exactly the rows some portal view exposes from that table, for the signed-in user |
# MAGIC | Row policies `TO` the application's group | Apply to the portal only; pipelines and administrators are unaffected |
# MAGIC | Column-mask policies | Mask a value in the table itself for roles that may see it only masked |
# MAGIC | Default-deny | Any base table without a grain tag returns no rows to the portal |
# MAGIC
# MAGIC Unity Catalog enforces these policies behind a barrier that keeps a user's own conditions from running on rows the
# MAGIC policy removes, so errors can't reveal other users' values. The views keep their own claim check, so a missing tag
# MAGIC or a mis-targeted policy still leaves every user with only their own rows.
# MAGIC
# MAGIC Column-mask policies do the same for masked values: a role that may see a date of birth or a member id only masked
# MAGIC never reaches it unmasked, even through a mistaken grant.
# MAGIC
# MAGIC The functions read only governance tables, which carry no policy: Unity Catalog doesn't let a policy function read
# MAGIC a table that has its own policy. A redeploy replaces the functions in place, so the policies are never detached.
# MAGIC With `enforcement=views` this step removes any row policies a previous layered deploy created.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

from claims_kit.availability import classify_no_claim
from claims_kit.deploy import DEPLOY_CLAIM, apply_policies, apply_tags, deploy_policy_functions, remove_row_policies
from claims_kit.identity import require_governed_tags
from claims_kit.policies import coverage_problems, coverage_queries, policy_problems
from claims_kit.tags import load_tag_set

if ENFORCEMENT == "views":
    print("\n".join(remove_row_policies(ex, catalog=CATALOG, admin_sql=admin_sql)))
    dbutils.notebook.exit("enforcement=views: no row policies")  # noqa: F821

tags = load_tag_set(TAG_SET)
problems = require_governed_tags(w.api_client.do, tags)
if problems:
    raise RuntimeError("Governed tags are not ready: " + "; ".join(problems) +
                       ". Ask an account admin to create them (Admin Runbook), or use --var tag_set=stand_in for evaluation.")
rows = lambda q: [tuple(r) for r in spark.sql(q).collect()]  # noqa: E731,F821

# 1. Tags first, and check them before touching any policy. Existing policies stay attached throughout this notebook.
log = apply_tags(ex, catalog=CATALOG, tags=tags, admin_sql=admin_sql)
table_q, column_q = coverage_queries(ex, CATALOG)
problems = coverage_problems(ex, tags, rows(table_q), rows(column_q))
if problems:
    raise RuntimeError("Row policy coverage problems: " + "; ".join(problems))

# 2. Replace the functions in place (a claim session in throw mode), then 3. create or replace the policies.
behavior = classify_no_claim(lambda q: spark.sql(q).collect()[0][0])  # noqa: F821
mode = "null" if behavior == "null" else "throws"
log += deploy_policy_functions(ex, catalog=CATALOG, portal_sp=portal_sp(), view_owner=VIEW_OWNER, mode=mode,
                               admin_sql=admin_sql, sp_runner=sp_runner(DEPLOY_CLAIM) if mode == "throws" else None)
log += apply_policies(ex, catalog=CATALOG, tags=tags, group=ex.portal_group, admin_sql=admin_sql)
print("\n".join(line[:160] for line in log))

# COMMAND ----------

# MAGIC %md
# MAGIC ### Check what was deployed
# MAGIC Every row-filter policy, column-mask policy and default-deny must exist on the base schema. Coverage was checked
# MAGIC before any policy changed: a missing tag would leave a table unfiltered by its policy, and a second tagged column
# MAGIC would make a policy ambiguous.

# COMMAND ----------

names = [r[0] for r in rows(f"SHOW POLICIES ON SCHEMA `{CATALOG}`.`{ex.schemas['base']}`")]
problems = policy_problems(ex, names, "layered")
if problems:
    raise RuntimeError("; ".join(problems))
print(f"policies ok: {len(names)} on the base schema, tag set {TAG_SET}")
