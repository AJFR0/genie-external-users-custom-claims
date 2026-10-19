from datetime import date

import pytest

from claims_kit.sql import StatementError, StatementRunner, render_template, split_sql
from conftest import FakeResponse


def test_split_sql_respects_quotes_comments_and_backticks():
    script = """
    -- leading comment; with semicolon
    CREATE VIEW `a;b`.v COMMENT 'x; y' AS SELECT 1;  /* block ; comment */
    SELECT "q;q", 'it''s;' ;
    SELECT 'back\\';slash';
    """
    assert split_sql(script) == [
        "CREATE VIEW `a;b`.v COMMENT 'x; y' AS SELECT 1",
        "SELECT \"q;q\", 'it''s;'",
        "SELECT 'back\\';slash'",
    ]


def test_split_sql_drops_empty_and_comment_only():
    assert split_sql("-- only\n;\n/* x */;") == []


def test_render_template_replaces_and_rejects_unknown():
    assert render_template("`{{catalog}}`.{{ gov }}", {"catalog": "c", "gov": "g"}) == "`c`.g"
    with pytest.raises(KeyError):
        render_template("{{missing}}", {})


@pytest.mark.parametrize("bad", ["a`b", "a'b", 'a"b', "a;b", "a\nb"])
def test_render_template_rejects_unsafe_values(bad):
    with pytest.raises(ValueError):
        render_template("{{x}}", {"x": bad})


def _ok(rows, cols=("c",), sid="s1", link=None):
    result = {"data_array": rows}
    if link:
        result["next_chunk_internal_link"] = link
    return FakeResponse(200, {"statement_id": sid, "status": {"state": "SUCCEEDED"},
                              "manifest": {"schema": {"columns": [{"name": c} for c in cols]}}, "result": result})


def test_execute_success_sends_body_and_auth(fake_http):
    fake_http.route("POST", "/api/2.0/sql/statements", _ok([["1"]]))
    r = StatementRunner("https://h", "wh", lambda: {"Authorization": "Bearer t"}, http=fake_http)
    res = r.execute("SELECT 1", {"uid": "pu-1", "n": 3, "flag": True, "d": date(2026, 1, 2), "none": None})
    call = fake_http.calls[0]
    assert call["headers"] == {"Authorization": "Bearer t"}
    assert call["json"]["warehouse_id"] == "wh" and call["json"]["format"] == "JSON_ARRAY"
    assert call["json"]["parameters"] == [
        {"name": "uid", "value": "pu-1", "type": "STRING"},
        {"name": "n", "value": "3", "type": "INT"},
        {"name": "flag", "value": "true", "type": "BOOLEAN"},
        {"name": "d", "value": "2026-01-02", "type": "DATE"},
        {"name": "none", "type": "STRING"},
    ]
    assert res.scalar() == "1" and res.dicts() == [{"c": "1"}]


def test_execute_polls_pending(fake_http):
    fake_http.route("POST", "/api/2.0/sql/statements", FakeResponse(200, {"statement_id": "s9", "status": {"state": "PENDING"}}))
    fake_http.route("GET", "/api/2.0/sql/statements/s9", [FakeResponse(200, {"statement_id": "s9", "status": {"state": "RUNNING"}}), _ok([["2"]], sid="s9")])
    r = StatementRunner("https://h", "wh", lambda: {}, http=fake_http, sleep=lambda s: None)
    assert r.execute("SELECT 2").scalar() == "2"


def test_execute_failure_raises_with_error_class(fake_http):
    fake_http.route("POST", "/api/2.0/sql/statements", FakeResponse(200, {"statement_id": "s2", "status": {"state": "FAILED", "error": {
        "error_code": "BAD_REQUEST", "message": "[OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED] No custom identity claim was provided."}}}))
    with pytest.raises(StatementError) as err:
        StatementRunner("https://h", "wh", lambda: {}, http=fake_http).execute("SELECT 1")
    assert err.value.error_class == "OAUTH_CUSTOM_IDENTITY_CLAIM_NOT_PROVIDED" and err.value.statement_id == "s2"


def test_execute_http_error(fake_http):
    fake_http.route("POST", "/api/2.0/sql/statements", FakeResponse(403, {"error_code": "PERMISSION_DENIED", "message": "no"}))
    with pytest.raises(StatementError) as err:
        StatementRunner("https://h", "wh", lambda: {}, http=fake_http).execute("SELECT 1")
    assert err.value.http_status == 403 and err.value.is_permission_error


def test_execute_follows_chunks(fake_http):
    fake_http.route("POST", "/api/2.0/sql/statements", _ok([["a"]], link="/api/2.0/sql/statements/s1/result/chunks/1"))
    fake_http.route("GET", "/chunks/1", FakeResponse(200, {"data_array": [["b"]]}))
    res = StatementRunner("https://h", "wh", lambda: {}, http=fake_http).execute("SELECT x")
    assert res.rows == [["a"], ["b"]]


@pytest.mark.parametrize("msg,denied", [
    ("[INSUFFICIENT_PERMISSIONS] Insufficient privileges: User does not have USE SCHEMA", True),
    ("[TABLE_OR_VIEW_NOT_FOUND] The table or view cannot be found", True),
    ("[DIVIDE_BY_ZERO] division by zero", False),
])
def test_denied_or_hidden(msg, denied):
    assert StatementError(msg).is_denied_or_hidden is denied
