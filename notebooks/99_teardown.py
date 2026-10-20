# Databricks notebook source
# MAGIC %md
# MAGIC # 99 · Tear down
# MAGIC Drops both examples' schemas and Genie Agents. With `delete_identities = true` it also deletes the two portal
# MAGIC service principals and the secret scope. The catalog itself is left in place.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

from claims_kit.deploy import remove_row_policies
from claims_kit.genie_space import find_space_by_title, space_title
from claims_kit.identity import delete_account_group

for name in ("northwind", "larkspur"):
    e = load_example(name)
    space_id = find_space_by_title(w.api_client.do, space_title(e.load_yaml("genie.yml"), CATALOG))
    if space_id:
        w.api_client.do("DELETE", f"/api/2.0/genie/spaces/{space_id}")
        print(f"deleted Genie Agent for {name}")
    try:
        print("\n".join(remove_row_policies(e, catalog=CATALOG, admin_sql=admin_sql)))
    except Exception as exc:  # the schemas may already be gone
        print(f"row policies for {name}: {str(exc)[:120]}")
    for logical in ("portal", "governance", "base"):
        admin_sql(f"DROP SCHEMA IF EXISTS `{CATALOG}`.`{e.schemas[logical]}` CASCADE")

if param("delete_identities", "false") == "true":
    for name in ("northwind", "larkspur"):
        for sp in w.service_principals.list(filter=f'displayName eq "genie-claims-ref-{name}-portal"'):
            w.service_principals.delete(sp.id)
            print(f"deleted service principal for {name}")
        if delete_account_group(w.api_client.do, load_example(name).portal_group):
            print(f"deleted account group for {name}")
    if SECRET_SCOPE in {s.name for s in w.secrets.list_scopes()}:
        w.secrets.delete_scope(SECRET_SCOPE)
        print(f"deleted secret scope {SECRET_SCOPE}")
