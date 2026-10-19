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

GUIDES = (("overview", "Genie for External Users: Who It Is For and What Changes"),
          ("implementation-guide", "Implementation Guide"),
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


def context() -> dict:
    values = {name: {k: _money(v) for k, v in load_fixtures(load_example(name)).genie_values.items()} for name in EXAMPLES}
    return {"values": values, "sql": sql_block, "diagram": diagram, "trace_card": trace_card, "validation_summary": validation_summary}


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
