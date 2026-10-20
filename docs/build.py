"""Render docs/src/*.md into self-contained HTML (docs/site) and PDF (docs/pdf).

Run:  .venv/bin/python -m docs.build            (macOS needs DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib for the PDFs)
      .venv/bin/python -m docs.build --no-pdf
Markdown is rendered as a Jinja template first, with [[ ]] and [% %] delimiters so SQL placeholders like {{catalog}}
stay literal. Numbers in the guides come from the deterministic generators, so they always match the deployed data.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

import jinja2
import markdown
from pygments.formatters import HtmlFormatter

DOCS = Path(__file__).resolve().parent
REPO = DOCS.parent
for p in (str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from claims_kit.config import load_example  # noqa: E402
from claims_kit.personas import load_fixtures  # noqa: E402
from claims_kit.policies import policy_sql  # noqa: E402
from claims_kit.tags import load_tag_set  # noqa: E402

GUIDES = (("overview", "Genie for External Users: Who It Is For and What Changes"),
          ("choosing-an-enforcement-model", "Choosing an Enforcement Model"),
          ("implementation-guide", "Implementation Guide"),
          ("admin-runbook", "Admin Runbook"),
          ("demo-runbook", "Demo Runbook"))
EXAMPLES = ("northwind", "larkspur")
FENCE = "`" * 3


def _money(v) -> str:
    return f"${v:,.2f}"


def sql_block(example: str, key: str) -> str:
    text = load_example(example).sql[key].read_text(encoding="utf-8").strip()
    return f"{FENCE}sql\n{text}\n{FENCE}"


def diagram(name: str, caption: str = "") -> str:
    svg = re.sub(r"<\?xml[^>]*\?>", "", (DOCS / "assets" / "diagrams" / f"{name}.svg").read_text(encoding="utf-8"))
    return f'<figure class="diagram">{svg}<figcaption>{html.escape(caption)}</figcaption></figure>'


def _evidence(example: str, kind: str):
    path = DOCS / "evidence" / f"{example}-{kind}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _table(columns, rows) -> str:
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def trace_card(example: str, persona_id: str) -> str:
    ev = _evidence(example, "trace-cards")
    if ev is None:
        return '<p class="missing">Run the isolation suite with --evidence to generate this card.</p>'
    card = next(c for c in ev["cards"] if c["persona"] == persona_id)
    shown = ("role", "scope_type", "scope_id", "valid_to")
    cols = card["grants"]["columns"]
    idx = [cols.index(c) for c in shown if c in cols]
    rows = [["open-ended" if r[i] is None and cols[i] == "valid_to" else r[i] for i in idx] for r in card["grants"]["rows"]]
    grants = (_table([cols[i] for i in idx], rows) if rows
              else "<p><b>No active grants.</b> Every portal view returns no rows.</p>")
    counts = "".join(f"<li><code>{html.escape(v)}</code>: <b>{n}</b> rows</li>" for v, n in card["view_row_counts"].items())
    return (f'<div class="trace-card"><div class="tc-head"><b>{html.escape(card["name"])}</b> · {html.escape(card["label"])} · '
            f'claim <code>{html.escape(card["claim"])}</code></div><ol class="tc-route">'
            f'<li>The token carries <code>custom.claim = {html.escape(card["claim"])}</code>.</li>'
            f'<li><code>my_effective_grants</code> keeps the grants for this claim and this service principal that are active today, '
            f'joined to their role policy:{grants}</li><li>The portal views return:<ul>{counts}</ul></li></ol>'
            f'<p class="tc-note">{html.escape(card["blurb"])} Observed on a live workspace on {html.escape(ev["run_date"])}.</p></div>')


def validation_summary(example: str) -> str:
    ev = _evidence(example, "validation")
    if ev is None:
        return '<p class="missing">Run the isolation suite with --evidence to generate this table.</p>'
    rows: dict[str, list[int]] = {}
    for r in ev["results"]:
        c = rows.setdefault(r["category"], [0, 0, 0])
        c[0 if r["passed"] is True else 1 if r["passed"] is False else 2] += 1
    body = [[cat, p, f, n] for cat, (p, f, n) in rows.items()]
    return (f'<div class="evidence">{_table(["category", "pass", "fail", "inconclusive or note"], body)}'
            f'<p class="dim">{html.escape(ev["example"].title())}, live run on {html.escape(ev["run_date"])}.</p></div>')


def _outcome(observed: str) -> str:
    if observed.startswith("leaked"):
        return "leaked: " + observed.split(":", 1)[1].split(" only")[0].strip()
    return observed.split(":", 1)[0]


def probe_comparison(example: str) -> str:
    """Side-channel probes: what each returned with views alone and with the layered model."""
    layered, views = _evidence(example, "validation"), _evidence(example, "views-mode-validation")
    if layered is None or views is None:
        return '<p class="missing">Run the isolation suite in both modes with --evidence to generate this table.</p>'
    sources = {p.id: p.source for p in load_fixtures(load_example(example)).probes}

    def by_id(ev):
        return {r["case_id"].split("/", 1)[1]: r for r in ev["results"] if r["case_id"].startswith("side_channel/")}

    lay, vw = by_id(layered), by_id(views)
    rows = [[pid, lay[pid]["persona"], sources.get(pid, ""), _outcome(vw[pid]["observed"]), _outcome(lay[pid]["observed"])]
            for pid in lay if pid in vw]
    return (f'<div class="evidence">{_table(["probe", "persona", "looks for", "Views only", "Layered"], rows)}'
            f'<p class="dim">{html.escape(example.title())}, live runs on {html.escape(views["run_date"])} (views only) and '
            f'{html.escape(layered["run_date"])} (layered).</p></div>')


def drills_summary(example: str) -> str:
    ev = _evidence(example, "drills")
    if ev is None:
        return '<p class="missing">Run python -m claims_kit.drills with --evidence to generate this table.</p>'
    label = {True: "held", False: "leak", None: "inconclusive"}
    rows = [[r["drill_id"], r["mistake"], f"{r['layered_rows']} rows (expected {r['expected_rows']})",
             f"{r['single_layer_rows']} of {r['total_rows']} rows", label[r["passed"]]] for r in ev["results"]]
    return (f'<div class="evidence">{_table(["drill", "mistake", "layered, with the mistake", "one layer alone", "result"], rows)}'
            f'<p class="dim">{html.escape(example.title())}, persona {html.escape(str(ev.get("persona")))}, live run on '
            f'{html.escape(ev["run_date"])}. Every drill restored and verified the original state.</p></div>')


def policy_example(example: str, table: str) -> str:
    ex = load_example(example)
    rp = next(r for r in ex.row_policies if r.table == table)
    return f"{FENCE}sql\n{policy_sql(ex, '<catalog>', load_tag_set('governed'), rp, ex.portal_group)}\n{FENCE}"


def context() -> dict:
    values = {name: {k: _money(v) for k, v in load_fixtures(load_example(name)).genie_values.items()} for name in EXAMPLES}
    return {"values": values, "sql": sql_block, "diagram": diagram, "trace_card": trace_card, "validation_summary": validation_summary,
            "probe_comparison": probe_comparison, "drills_summary": drills_summary, "policy_example": policy_example}


def render(slug: str, title: str, ctx: dict, css: str) -> str:
    env = jinja2.Environment(variable_start_string="[[", variable_end_string="]]", block_start_string="[%",
                             block_end_string="%]", comment_start_string="[#", comment_end_string="#]",
                             undefined=jinja2.StrictUndefined)
    text = env.from_string((DOCS / "src" / f"{slug}.md").read_text(encoding="utf-8")).render(**ctx)
    md = markdown.Markdown(extensions=["tables", "fenced_code", "codehilite", "toc", "attr_list", "admonition", "md_in_html"],
                           extension_configs={"codehilite": {"guess_lang": False}, "toc": {"toc_depth": "2-3"}})
    body = md.convert(text)
    page = jinja2.Template((DOCS / "templates" / "guide.html.j2").read_text(encoding="utf-8"))
    return page.render(title=title, body=body, toc=md.toc, css=css, guides=GUIDES, slug=slug)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build the HTML and PDF guides")
    parser.add_argument("--no-pdf", action="store_true")
    args = parser.parse_args(argv)
    css = (DOCS / "templates" / "guide.css").read_text(encoding="utf-8") + HtmlFormatter(style="friendly").get_style_defs(".codehilite")
    ctx = context()
    (DOCS / "site").mkdir(exist_ok=True)
    (DOCS / "pdf").mkdir(exist_ok=True)
    for slug, title in GUIDES:
        page = render(slug, title, ctx, css)
        (DOCS / "site" / f"{slug}.html").write_text(page, encoding="utf-8")
        if not args.no_pdf:
            from weasyprint import HTML
            HTML(string=page, base_url=str(DOCS / "site")).write_pdf(DOCS / "pdf" / f"{slug}.pdf")
        print(f"built {slug}")


if __name__ == "__main__":
    main()
