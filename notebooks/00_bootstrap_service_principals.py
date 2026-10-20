# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Bootstrap the portal service principals
# MAGIC Run once, as a workspace admin. Each example **application** gets its own service principal:
# MAGIC
# MAGIC | Service principal | Represents |
# MAGIC |---|---|
# MAGIC | `genie-claims-ref-northwind-portal` | the Northwind Retirement portal backend |
# MAGIC | `genie-claims-ref-larkspur-portal` | the Larkspur Pharmacy Benefits portal backend |
# MAGIC
# MAGIC One service principal per application is what lets the views prove **layered security**: a view only
# MAGIC answers for its own application's service principal, even if someone grants another application access.
# MAGIC
# MAGIC This notebook creates each service principal (with workspace and SQL access), creates an OAuth secret,
# MAGIC stores the client id and secret in the secret scope, and grants `CAN USE` on the SQL warehouse.
# MAGIC In production the secret lives in your own vault, or you use workload identity federation and store none.
# MAGIC
# MAGIC It also creates one **account group** per application, `genie-claims-ref-<example>-portal-backends`, with the
# MAGIC service principal as its only member. Grants and row policies name the group, so you can rotate or replace the
# MAGIC service principal by changing membership, with no grant or policy changes. New memberships can take a few
# MAGIC minutes to reach Unity Catalog.
# MAGIC
# MAGIC With `tag_set=governed` (the default), it also tries to create the two governed tags the row policies use,
# MAGIC `portal_grain` and `portal_key`. Creating governed tags needs account-level permission; if you don't have it,
# MAGIC the notebook prints what to ask an account admin for. Keep ASSIGN on these tags to a small governance group.

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

from databricks.sdk.service import iam
from databricks.sdk.service import sql as dbsql

from claims_kit.identity import add_portal_member, create_governed_tags
from claims_kit.tags import load_tag_set

EXAMPLES = [e.strip() for e in param("examples", "northwind,larkspur").split(",") if e.strip()]
ROTATE = param("rotate_secrets", "false") == "true"

if SECRET_SCOPE not in {s.name for s in w.secrets.list_scopes()}:
    w.secrets.create_scope(scope=SECRET_SCOPE)
existing_keys = {k.key for k in w.secrets.list_secrets(scope=SECRET_SCOPE)}

for name in EXAMPLES:
    display = f"genie-claims-ref-{name}-portal"
    found = list(w.service_principals.list(filter=f'displayName eq "{display}"'))
    sp = found[0] if found else w.service_principals.create(
        display_name=display, active=True,
        entitlements=[iam.ComplexValue(value="workspace-access"), iam.ComplexValue(value="databricks-sql-access")])
    if ROTATE or f"{name}-client-secret" not in existing_keys:
        secret = w.service_principal_secrets_proxy.create(service_principal_id=sp.id)
        w.secrets.put_secret(scope=SECRET_SCOPE, key=f"{name}-client-id", string_value=sp.application_id)
        w.secrets.put_secret(scope=SECRET_SCOPE, key=f"{name}-client-secret", string_value=secret.secret)
    w.warehouses.update_permissions(warehouse_id=WAREHOUSE_ID, access_control_list=[
        dbsql.WarehouseAccessControlRequest(service_principal_name=sp.application_id,
                                            permission_level=dbsql.WarehousePermissionLevel.CAN_USE)])
    print(f"{name}: {display} ready (application id {sp.application_id})")
    group = load_example(name).portal_group
    add_portal_member(w.api_client.do, group, sp.id)
    print(f"{name}: account group {group} has the portal service principal as its only member")

# COMMAND ----------

TAG_SET_NAME = param("tag_set", "governed")
if TAG_SET_NAME == "governed":
    print("\n".join(create_governed_tags(w.api_client.do, load_tag_set(TAG_SET_NAME))))
else:
    print(f"tag_set={TAG_SET_NAME}: no governed tags created (evaluation only)")
