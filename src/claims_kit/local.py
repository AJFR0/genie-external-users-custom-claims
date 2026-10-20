"""Local settings for the CLIs and the reference app: environment variables, optionally from .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

EXAMPLE_NAMES = ("northwind", "larkspur")


def read_env(environ: dict | None = None, dotenv_path: str | Path = ".env") -> dict[str, str]:
    """Values from a simple KEY=VALUE .env file, overridden by real environment variables."""
    merged: dict[str, str] = {}
    path = Path(dotenv_path)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            merged[key.strip()] = value.strip().strip("'\"")
    merged.update(os.environ if environ is None else environ)
    return merged


@dataclass(frozen=True)
class ExampleCreds:
    client_id: str
    client_secret: str
    genie_space_id: str | None


@dataclass(frozen=True)
class LocalEnv:
    host: str
    warehouse_id: str
    admin_profile: str | None
    catalog: str
    examples: dict
    enforcement: str = "layered"
    tag_set: str = "governed"

    @classmethod
    def from_mapping(cls, m: dict) -> "LocalEnv":
        examples = {}
        for name in EXAMPLE_NAMES:
            prefix = name.upper()
            if m.get(f"{prefix}_CLIENT_ID"):
                examples[name] = ExampleCreds(m[f"{prefix}_CLIENT_ID"], m[f"{prefix}_CLIENT_SECRET"], m.get(f"{prefix}_GENIE_SPACE_ID") or None)
        enforcement = m.get("ENFORCEMENT") or "layered"
        if enforcement not in ("layered", "views"):
            raise ValueError(f"ENFORCEMENT must be layered or views, not {enforcement!r}")
        return cls(host=m["DATABRICKS_HOST"].rstrip("/"), warehouse_id=m["WAREHOUSE_ID"], admin_profile=m.get("ADMIN_PROFILE") or None,
                   catalog=m.get("CATALOG") or "genie_claims_ref", examples=examples, enforcement=enforcement,
                   tag_set=m.get("TAG_SET") or "governed")


def admin_client(profile: str | None):
    """The operator's own Databricks identity (CLI profile). Never a portal service principal."""
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient(profile=profile) if profile else WorkspaceClient()
