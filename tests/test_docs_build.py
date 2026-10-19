from docs.build import GUIDES, context, render


def test_every_guide_renders_without_unresolved_helpers():
    ctx = context()
    for slug, title in GUIDES:
        html = render(slug, title, ctx, css="")
        assert "<svg" in html and "[[" not in html and "[%" not in html, slug
        assert "Community reference, not official Databricks documentation" in html
        assert "\u2014" not in html, f"{slug}: no em dashes"


def test_sql_helper_keeps_template_placeholders():
    assert "{{catalog}}" in context()["sql"]("northwind", "policy_views")
