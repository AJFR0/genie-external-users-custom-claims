"""Tag sets for the row policies: which governed tags mark a table's grain and bind a policy's key columns.

config/tags.yml names the logical tags once. A tag set maps each one to a real governed tag:
  governed  two custom governed tags an account admin creates (portal_grain, portal_key), each with values
  stand_in  key-only platform system tags, for evaluation workspaces where you can't create governed tags
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

TAGS_FILE = Path(__file__).resolve().parents[2] / "config" / "tags.yml"
TAG_SETS = ("governed", "stand_in")
_SAFE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]{0,62}$")


@dataclass(frozen=True)
class Tag:
    key: str
    value: str | None = None

    def __post_init__(self):
        for part in (self.key, self.value):
            if part is not None and not _SAFE.match(part):
                raise ValueError(f"unsafe tag name {part!r}")

    def condition(self) -> str:
        """The policy condition that matches this tag."""
        return f"has_tag_value('{self.key}', '{self.value}')" if self.value else f"has_tag('{self.key}')"

    def assignment(self) -> str:
        """The body of SET TAGS (...)."""
        return f"'{self.key}' = '{self.value}'" if self.value else f"'{self.key}'"


@dataclass(frozen=True)
class TagSet:
    name: str
    grains: dict
    keys: dict

    def grain(self, logical: str) -> Tag:
        return self.grains[logical]

    def key(self, logical: str) -> Tag:
        return self.keys[logical]

    def any_grain(self) -> str:
        """True for a table with any grain tag. Default-deny applies to every table without one."""
        return " OR ".join(sorted({f"has_tag('{t.key}')" for t in self.grains.values()}))


def load_tag_set(name: str, path: Path = TAGS_FILE) -> TagSet:
    if name not in TAG_SETS:
        raise ValueError(f"unknown tag set {name!r}; use one of {TAG_SETS}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    grains, keys, spec = list(raw["grains"]), list(raw["keys"]), raw["sets"][name]
    if "grain_key" in spec:
        return TagSet(name, {g: Tag(spec["grain_key"], g) for g in grains}, {k: Tag(spec["key_key"], k) for k in keys})
    missing = [g for g in grains if g not in spec["grains"]] + [k for k in keys if k not in spec["keys"]]
    if missing:
        raise ValueError(f"tag set {name}: no mapping for {missing}")
    tagset = TagSet(name, {g: Tag(spec["grains"][g]) for g in grains}, {k: Tag(spec["keys"][k]) for k in keys})
    used = [t.key for t in (*tagset.grains.values(), *tagset.keys.values())]
    reused = sorted({k for k in used if used.count(k) > 1})
    if reused:
        raise ValueError(f"tag set {name}: each logical tag needs its own key, reused {reused}")
    return tagset
