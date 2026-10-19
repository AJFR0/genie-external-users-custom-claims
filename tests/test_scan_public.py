import subprocess

import pytest

from scripts.scan_public import scan_repo, scan_text

TOKEN_LIKE = "dapi" + "0" * 32
HOST_LIKE = "acme-prod" + ".cloud.databricks" + ".com"


def test_builtin_rules_flag_host_token_uuid_and_stage_claims():
    text = "\n".join([
        f"host = {HOST_LIKE}",
        f"token {TOKEN_LIKE}",
        "id 1b4c2f0e-1111-2222-3333-" + "444455556666",
        "This is " + "not " + "GA" + " yet",
        "a fine line",
    ])
    rules = {rule for _, rule, _ in scan_text(text, [])}
    assert {"workspace host", "personal access token", "uuid", "release-stage claim"} <= rules


def test_denylist_terms_match_whole_words_case_insensitive():
    hits = scan_text("Built for Contoso Bank last year\ncontosobankish", ["contoso bank"])
    assert [line for line, _, _ in hits] == [1]


def test_markdown_anchor_is_not_a_slack_channel():
    assert scan_text("[see](#how-it-works-step-by-step)", []) == []


def test_scan_allow_marker_skips_line():
    assert scan_text(f"pattern {TOKEN_LIKE}  # scan:allow", []) == []


def test_scan_repo_counts_files_and_lists_images(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "a.md").write_text("clean text\n")
    (tmp_path / "b.png").write_bytes(b"\x89PNG")
    findings, review, scanned = scan_repo(tmp_path, [])
    assert findings == [] and scanned == 1 and [p.name for p in review] == ["b.png"]


def test_scan_repo_with_no_files_raises(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    with pytest.raises(RuntimeError, match="scanned 0 files"):
        scan_repo(tmp_path, [])
