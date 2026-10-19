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

# COMMAND ----------

# MAGIC %pip install -q -r ../requirements-notebooks.txt

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------

# MAGIC %run ./_common

# COMMAND ----------

from databricks.sdk.service import iam
from databricks.sdk.service import sql as dbsql

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
