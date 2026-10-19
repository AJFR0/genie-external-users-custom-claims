#!/usr/bin/env python3
"""Write the local .env from the bundle's secret scope (run as the operator; .env is gitignored)."""
from __future__ import annotations

import argparse
import base64
from pathlib import Path

from databricks.sdk import WorkspaceClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--scope", default="genie-claims-ref")
    parser.add_argument("--catalog", default="genie_claims_ref")
    args = parser.parse_args()
    w = WorkspaceClient(profile=args.profile)
    values = {"DATABRICKS_HOST": w.config.host.rstrip("/"), "WAREHOUSE_ID": args.warehouse_id, "ADMIN_PROFILE": args.profile,
              "CATALOG": args.catalog, "BUNDLE_VAR_warehouse_id": args.warehouse_id, "BUNDLE_VAR_catalog": args.catalog}
    for name in ("northwind", "larkspur"):
        for key, env in (("client-id", "CLIENT_ID"), ("client-secret", "CLIENT_SECRET")):
            secret = w.secrets.get_secret(scope=args.scope, key=f"{name}-{key}")
            values[f"{name.upper()}_{env}"] = base64.b64decode(secret.value).decode()
    path = Path(".env")
    existing = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                existing[k] = v
    existing.update(values)
    path.write_text("".join(f"{k}={v}\n" for k, v in existing.items()))
    print(f"wrote {len(values)} values to {path.resolve()} (gitignored)")


if __name__ == "__main__":
    main()
