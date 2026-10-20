from app_fakes import FakeGenie, FakeRunner, make_client
from claims_kit.sql import StatementError

TITLES = ["Session → portal user id", "Claim format check", "Token for the portal service principal, stamped with the claim",
          "Genie conversation, bound to this user on the server", "SQL written by Genie",
          "Why these rows: entitlements resolved from the claim", "Row policies under the views", "Rows returned",
          "Audit record written"]


def sign_in(client, persona="maya"):
    r = client.post("/portal/sign-in", data={"example": "northwind", "persona": persona}, follow_redirects=False)
    assert r.status_code == 303


def test_ask_requires_sign_in(tmp_path):
    client, *_ = make_client(tmp_path)
    assert client.post("/portal/api/ask", json={"question": "hi"}).status_code == 401


def test_sign_in_and_ask_returns_nine_step_trace(tmp_path):
    client, services, genie, runner = make_client(tmp_path)
    sign_in(client)
    body = client.post("/portal/api/ask", json={"question": "What is my balance?"}).json()
    assert [s["title"] for s in body["trace"]] == TITLES and all(s["status"] == "ok" for s in body["trace"])
    assert body["trace"][2]["detail"]["decoded_payload"]["custom"] == {"claim": "pu-1001"}
    assert body["answer"]["status"] == "COMPLETED" and services.conversations.get("northwind", "pu-1001") == "conv-1"
    assert "northwind_portal" in runner.calls[0][0] and "my_access" in runner.calls[0][0]


def test_follow_up_reuses_server_side_conversation(tmp_path):
    client, _, genie, _ = make_client(tmp_path)
    sign_in(client)
    client.post("/portal/api/ask", json={"question": "q1"})
    client.post("/portal/api/ask", json={"question": "q2"})
    client.post("/portal/api/ask", json={"question": "q3", "new_conversation": True})
    assert [cid for _, cid in genie.asked] == [None, "conv-1", None]


def test_ask_rejects_client_conversation_id(tmp_path):
    client, *_ = make_client(tmp_path)
    sign_in(client)
    assert client.post("/portal/api/ask", json={"question": "q", "conversation_id": "someone-elses"}).status_code == 422
    assert client.post("/portal/api/ask", json={"question": "q", "claim": "pu-1002"}).status_code == 422


def test_switching_persona_deletes_previous_conversation(tmp_path):
    client, services, genie, _ = make_client(tmp_path)
    sign_in(client, "maya")
    client.post("/portal/api/ask", json={"question": "q1"})
    sign_in(client, "james")
    assert genie.deleted == ["conv-1"] and services.conversations.get("northwind", "pu-1001") is None
    client.post("/portal/api/ask", json={"question": "q2"})
    assert genie.asked[-1][1] is None and services.conversations.get("northwind", "pu-1002") == "conv-2"


def test_sign_out_deletes_conversation_and_forgets_token(tmp_path):
    client, services, genie, _ = make_client(tmp_path)
    sign_in(client)
    client.post("/portal/api/ask", json={"question": "q1"})
    client.post("/portal/sign-out", follow_redirects=False)
    assert genie.deleted == ["conv-1"] and services.examples["northwind"].provider.forgotten == ["pu-1001"]
    assert client.post("/portal/api/ask", json={"question": "q"}).status_code == 401


def test_ask_failed_genie_status_is_warn(tmp_path):
    client, *_ = make_client(tmp_path, genie=FakeGenie(status="FAILED"))
    sign_in(client)
    body = client.post("/portal/api/ask", json={"question": "q"}).json()
    assert body["answer"]["status"] == "FAILED" and body["trace"][3]["status"] == "warn" and body["error"] is None


def test_my_access_step_error_is_reported(tmp_path):
    client, *_ = make_client(tmp_path, runner=FakeRunner(error=StatementError("[INSUFFICIENT_PERMISSIONS] no")))
    sign_in(client)
    body = client.post("/portal/api/ask", json={"question": "q"}).json()
    assert "INSUFFICIENT_PERMISSIONS" in body["error"] and body["trace"][-1]["status"] == "error"


def test_audit_records_sign_in_and_ask(tmp_path):
    client, services, *_ = make_client(tmp_path)
    sign_in(client)
    client.post("/portal/api/ask", json={"question": "q"})
    events = services.audit.tail()
    assert [e["event"] for e in events] == ["sign_in", "ask"] and events[1]["statement_ids"] == ["stmt-1"]


def test_redact_ids_masks_token_fields(tmp_path):
    client, *_ = make_client(tmp_path, redact_ids=True)
    sign_in(client)
    payload = client.post("/portal/api/ask", json={"question": "q"}).json()["trace"][2]["detail"]["decoded_payload"]
    assert payload["aud"] == "1234…" and payload["custom"] == {"claim": "pu-1001"}


def test_portal_page_renders(tmp_path):
    client, *_ = make_client(tmp_path)
    assert "Maya" in client.get("/portal").text


def test_redact_mode_hides_the_catalog_name(tmp_path):
    sql = "SELECT SUM(balance) FROM `cat`.`northwind_portal`.`my_accounts`"
    client, *_ = make_client(tmp_path, genie=FakeGenie(sql=sql), redact_ids=True)
    sign_in(client)
    body = client.post("/portal/api/ask", json={"question": "q"}).json()
    text = str(body)
    assert "`<catalog>`.`northwind_portal`" in text and "`cat`" not in text


def test_without_redact_mode_sql_is_shown_as_is(tmp_path):
    sql = "SELECT 1 FROM `cat`.`northwind_portal`.`my_accounts`"
    client, *_ = make_client(tmp_path, genie=FakeGenie(sql=sql))
    sign_in(client)
    assert sql in str(client.post("/portal/api/ask", json={"question": "q"}).json())


def test_redact_mode_hides_statement_ids_everywhere(tmp_path):
    client, *_ = make_client(tmp_path, redact_ids=True)
    sign_in(client)
    body = client.post("/portal/api/ask", json={"question": "q"}).json()
    assert "stmt-1" not in str(body["trace"])


UUID = "0f8e7d6c-1111-2222-3333-" + "444455556666"


def test_redact_mode_scrubs_hosts_and_ids_from_errors(tmp_path):
    err = RuntimeError(f"GET https://host.example/api/2.0/genie/spaces/space-1 failed for {UUID} on wh-123")
    client, *_ = make_client(tmp_path, genie=FakeGenie(error=err), redact_ids=True, host="https://host.example")
    sign_in(client)
    text = str(client.post("/portal/api/ask", json={"question": "q"}).json())
    assert "host.example" not in text and UUID not in text and "wh-123" not in text and "<workspace-host>" in text


def test_untrusted_host_header_is_rejected(tmp_path):
    client, *_ = make_client(tmp_path)
    assert client.get("/portal", headers={"host": "evil.example"}).status_code == 400


def test_layered_trace_names_the_row_policy_layer(tmp_path):
    client, *_ = make_client(tmp_path)
    sign_in(client)
    step = client.post("/portal/api/ask", json={"question": "q"}).json()["trace"][6]
    assert step["title"] == "Row policies under the views" and step["detail"]["enforcement"] == "layered"


def test_views_mode_trace_says_there_are_no_row_policies(tmp_path):
    client, *_ = make_client(tmp_path, enforcement="views")
    sign_in(client)
    titles = [s["title"] for s in client.post("/portal/api/ask", json={"question": "q"}).json()["trace"]]
    assert "Views only: no row policies under the views" in titles and "Row policies under the views" not in titles
