"""Build a Genie Agent definition from genie.yml and create or update it idempotently.

Genie rejects tables that don't exist yet, so this runs after the claim-keyed views exist.
Prompt matching (format assistance and entity matching) samples column values with the author's
permissions and shares them with every user, so it is off for claim-keyed views and on only
for public reference views.
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable

Do = Callable[..., dict]


def stable_id(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def space_title(spec: dict, catalog: str) -> str:
    return f"{spec['title']} [{catalog}]"


def build_serialized_space(spec: dict, *, table_ids: dict[str, str], columns: dict[str, list[str]]) -> str:
    tables = []
    for t in spec["tables"]:
        key = t["view"]
        pm = bool(t.get("prompt_matching", False))
        configs = [{"column_name": c, "enable_format_assistance": pm, "enable_entity_matching": pm} for c in sorted(columns[key])]
        tables.append({"identifier": table_ids[key], "column_configs": configs})
    tables.sort(key=lambda e: e["identifier"])
    questions = sorted(({"id": stable_id(q), "question": [q]} for q in spec.get("sample_questions", [])), key=lambda e: e["id"])
    paragraphs = [p.strip() + "\n" for p in spec["instructions"].strip().split("\n\n") if p.strip()]
    space = {
        "version": 2,
        "config": {"sample_questions": questions},
        "data_sources": {"tables": tables},
        "instructions": {"text_instructions": [{"id": stable_id(spec["instructions"]), "content": paragraphs}]},
    }
    return json.dumps(space, indent=2)


def find_space_by_title(do: Do, title: str) -> str | None:
    token = None
    while True:
        query = {"page_size": 100}
        if token:
            query["page_token"] = token
        r = do("GET", "/api/2.0/genie/spaces", query=query)
        for s in r.get("spaces", []):
            if s.get("title") == title:
                return s["space_id"]
        token = r.get("next_page_token")
        if not token:
            return None


def upsert_space(do: Do, *, title: str, description: str, warehouse_id: str, parent_path: str, serialized_space: str) -> tuple[str, str]:
    body = {"title": title, "description": description, "warehouse_id": warehouse_id, "serialized_space": serialized_space}
    existing = find_space_by_title(do, title)
    if existing:
        do("PATCH", f"/api/2.0/genie/spaces/{existing}", body=body)
        return existing, "updated"
    r = do("POST", "/api/2.0/genie/spaces", body={**body, "parent_path": parent_path})
    return r["space_id"], "created"


def grant_can_run(do: Do, space_id: str, sp_application_id: str) -> None:
    do("PATCH", f"/api/2.0/permissions/genie/{space_id}",
       body={"access_control_list": [{"service_principal_name": sp_application_id, "permission_level": "CAN_RUN"}]})
