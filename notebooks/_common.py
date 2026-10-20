# Databricks notebook source
# MAGIC %md
# MAGIC ### Shared setup
# MAGIC Every notebook runs this with `%run ./_common`. It puts the repo's `src/` and `examples/` on the import
# MAGIC path, reads the job parameters, and builds the two kinds of SQL sessions this kit uses:
# MAGIC
# MAGIC | Session | Identity | Used for |
# MAGIC |---|---|---|
# MAGIC | `admin_sql(...)` | you (the job's run-as identity), no claim | schemas, tables, entitlements, grants, ownership |
# MAGIC | `sp_runner(claim)` | the example's **portal service principal**, with a custom claim | everything the portal does |
# MAGIC
# MAGIC Two job parameters choose the enforcement model: `enforcement` (`layered`, the default, adds ABAC row policies
# MAGIC under the claim-keyed views; `views` deploys the views only) and `tag_set` (`governed` custom tags, or `stand_in`
# MAGIC platform tags for evaluation workspaces).

# COMMAND ----------

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.getcwd(), ".."))
for _p in (os.path.join(REPO_ROOT, "src"), REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from databricks.sdk import WorkspaceClient  # noqa: E402

from claims_kit.config import load_example  # noqa: E402
from claims_kit.sql import StatementRunner, split_sql  # noqa: E402
from claims_kit.tokens import ClaimTokenProvider  # noqa: E402


def param(name, default=""):
    try:
        dbutils.widgets.text(name, default)  # noqa: F821
    except Exception:
        pass
    return dbutils.widgets.get(name).strip()  # noqa: F821


EXAMPLE = param("example", "northwind")
CATALOG = param("catalog", "genie_claims_ref")
WAREHOUSE_ID = param("warehouse_id")
SECRET_SCOPE = param("secret_scope", "genie-claims-ref")
ENFORCEMENT = param("enforcement", "layered")
TAG_SET = param("tag_set", "governed")
if ENFORCEMENT not in ("layered", "views"):
    raise ValueError(f"enforcement must be layered or views, not {ENFORCEMENT!r}")
w = WorkspaceClient()
HOST = w.config.host.rstrip("/")
VIEW_OWNER = param("view_owner") or w.current_user.me().user_name
ex = load_example(EXAMPLE)
_PROVIDERS = {}


def sp_credentials(name=EXAMPLE):
    return (dbutils.secrets.get(SECRET_SCOPE, f"{name}-client-id"),  # noqa: F821
            dbutils.secrets.get(SECRET_SCOPE, f"{name}-client-secret"))  # noqa: F821


def portal_sp(name=EXAMPLE):
    """The portal service principal's application id. It is also its OAuth client id."""
    return sp_credentials(name)[0]


def sp_provider(name=EXAMPLE):
    if name not in _PROVIDERS:
        client_id, secret = sp_credentials(name)
        _PROVIDERS[name] = ClaimTokenProvider(HOST, client_id, secret)
    return _PROVIDERS[name]


def sp_runner(claim, name=EXAMPLE):
    return StatementRunner(HOST, WAREHOUSE_ID, sp_provider(name).auth_for(claim))


def admin_sql(statement):
    print(f"admin> {' '.join(statement.split())[:140]}")
    return spark.sql(statement)  # noqa: F821


def run_admin_script(text):
    for statement in split_sql(text):
        admin_sql(statement)


def admin_runner():
    return StatementRunner(HOST, WAREHOUSE_ID, w.config.authenticate)
