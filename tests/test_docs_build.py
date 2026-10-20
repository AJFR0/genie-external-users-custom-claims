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


from docs.build import drills_summary, policy_example, probe_comparison


def test_guides_include_the_enforcement_model_and_admin_runbook():
    slugs = [slug for slug, _ in GUIDES]
    assert "choosing-an-enforcement-model" in slugs and "admin-runbook" in slugs


def test_drills_summary_renders_each_drill_from_evidence():
    html = drills_summary("northwind")
    assert "<table>" in html and "D1" in html and "D5" in html and "held" in html


def test_probe_comparison_shows_views_only_and_layered_outcomes():
    html = probe_comparison("larkspur")
    assert "Views only" in html and "Layered" in html and "theo-cell" in html
    assert "leaked" in html and "blocked" in html


def test_policy_example_is_the_generated_policy_sql():
    sql = policy_example("northwind", "base.account_balances")
    assert "CREATE OR REPLACE POLICY portal_accounts_rows" in sql and "has_tag_value('portal_grain', 'accounts')" in sql
    assert "<catalog>" in sql
