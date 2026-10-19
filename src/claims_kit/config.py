"""Load an example's definition (examples/<name>/example.yml) and compute object names."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .sql import render_template

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"
SQL_KEYS = ("schemas", "base_tables", "governance", "seed_entitlements", "policy_views", "portal_views", "public_views", "runtime_grants")
_REQUIRED = ("name", "title", "claim_prefix", "schemas", "sql", "claim_views", "public_views", "role_policy_fields", "grant_roles",
             "scope_types", "base_probe_table")


@dataclass(frozen=True)
class Example:
    name: str
    title: str
    claim_prefix: str
    root: Path
    schemas: dict
    sql: dict
    claim_views: tuple
    public_views: tuple
    role_policy_fields: dict
    grant_roles: tuple
    scope_types: tuple
    base_probe_table: str

    def fq(self, catalog: str, dotted: str) -> str:
        logical, obj = dotted.split(".", 1)
        return f"`{catalog}`.`{self.schemas[logical]}`.`{obj}`"

    @property
    def portal_views(self) -> tuple:
        return tuple(v.split(".", 1)[1] for v in self.claim_views if v.startswith("portal."))

    def template_values(self, catalog: str, portal_sp: str, view_owner: str) -> dict:
        return {"catalog": catalog, "base": self.schemas["base"], "gov": self.schemas["governance"],
                "portal": self.schemas["portal"], "portal_sp": portal_sp, "view_owner": view_owner}

    def read_sql(self, key: str, values: dict) -> str:
        return render_template(self.sql[key].read_text(encoding="utf-8"), values)

    def load_yaml(self, filename: str) -> dict:
        return yaml.safe_load((self.root / filename).read_text(encoding="utf-8"))


def load_example(name: str, examples_dir: Path = EXAMPLES_DIR) -> Example:
    path = examples_dir / name / "example.yml"
    if not path.exists():
        raise FileNotFoundError(f"no example definition at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    missing = [k for k in _REQUIRED if k not in raw] + [f"sql.{k}" for k in SQL_KEYS if k not in raw.get("sql", {})]
    if missing:
        raise ValueError(f"{path}: missing {missing}")
    root = path.parent
    return Example(
        name=raw["name"], title=raw["title"], claim_prefix=raw["claim_prefix"], root=root,
        schemas=dict(raw["schemas"]), sql={k: root / raw["sql"][k] for k in SQL_KEYS},
        claim_views=tuple(raw["claim_views"]), public_views=tuple(raw["public_views"]),
        role_policy_fields=dict(raw["role_policy_fields"]), grant_roles=tuple(raw["grant_roles"]),
        scope_types=tuple(raw["scope_types"]), base_probe_table=raw["base_probe_table"],
    )
