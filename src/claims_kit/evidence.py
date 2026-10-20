"""Publishable evidence from a live validation run: the results table and per-persona trace cards, scrubbed."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .personas import load_personas
from .trace import replace_identifier, scrub  # noqa: F401  (scrub is re-exported)
from .validate import results_as_dicts

TRACE_PERSONAS = {"northwind": ("linda", "raj", "unknown"), "larkspur": ("ana", "dana", "theo", "priya")}
def trace_card(ctx, persona) -> dict:
    runner = ctx.sp_runner(persona.claim)
    access = runner.execute(f"SELECT * FROM {ctx.view('my_access')}")
    counts = {view: int(runner.execute(f"SELECT count(*) FROM {ctx.view(view)}").scalar())
              for view in ctx.example.portal_views if view != "my_access"}
    return {"persona": persona.id, "name": persona.name, "label": persona.label, "claim": persona.claim, "blurb": persona.blurb,
            "grants": {"columns": access.columns, "rows": access.rows}, "view_row_counts": counts}


def write_evidence(ctx, results, out_dir: Path) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    secrets = {ctx.host: "https://<workspace-host>", ctx.warehouse_id: "<warehouse-id>", ctx.provider.client_id: "<portal-sp>"}
    if ctx.other_provider is not None:
        secrets[ctx.other_provider.client_id] = "<other-portal-sp>"
    personas = {p.id: p for p in load_personas(ctx.example)}
    meta = {"example": ctx.example.name, "run_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "catalog": ctx.catalog}
    # The catalog is deployment-specific, so it never goes into published evidence.
    def publishable(obj):
        return replace_identifier(scrub(obj, secrets), ctx.catalog, "<catalog>")

    validation = publishable({**meta, "results": results_as_dicts(results)})
    cards = publishable({**meta, "cards": [trace_card(ctx, personas[pid]) for pid in TRACE_PERSONAS[ctx.example.name]]})
    paths = [out_dir / f"{ctx.example.name}-validation.json", out_dir / f"{ctx.example.name}-trace-cards.json"]
    paths[0].write_text(json.dumps(validation, indent=2), encoding="utf-8")
    paths[1].write_text(json.dumps(cards, indent=2), encoding="utf-8")
    return paths


def write_drill_evidence(ctx, results, out_dir: Path, *, baseline: dict | None = None, persona: str | None = None) -> Path:
    """The misconfiguration drill results, scrubbed the same way as the validation evidence."""
    from .drills import results_as_dicts as drill_dicts
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    secrets = {ctx.host: "https://<workspace-host>", ctx.warehouse_id: "<warehouse-id>", ctx.provider.client_id: "<portal-sp>"}
    doc = {"example": ctx.example.name, "run_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "persona": persona,
           "baseline": baseline, "results": drill_dicts(results)}
    path = out_dir / f"{ctx.example.name}-drills.json"
    path.write_text(json.dumps(replace_identifier(scrub(doc, secrets), ctx.catalog, "<catalog>"), indent=2), encoding="utf-8")
    return path
