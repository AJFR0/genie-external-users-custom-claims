from claims_kit.genie import GenieClient
from conftest import FakeResponse

BASE = "/api/2.0/genie/spaces/sp1"


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _client(fake_http, clock=None, **kw):
    clock = clock or Clock()

    def sleep(s):
        clock.t += s
    return GenieClient("https://h", "sp1", lambda: {"Authorization": "Bearer t"}, http=fake_http, sleep=sleep, clock=clock, **kw)


def test_ask_new_conversation_polls_and_fetches_results(fake_http):
    fake_http.route("POST", f"{BASE}/start-conversation", FakeResponse(200, {"conversation_id": "c1", "message_id": "m1"}))
    fake_http.route("GET", f"{BASE}/conversations/c1/messages/m1/attachments/a1/query-result", FakeResponse(200, {"statement_response": {
        "statement_id": "st1", "manifest": {"schema": {"columns": [{"name": "total"}]}}, "result": {"data_array": [["123.45"]]}}}))
    fake_http.route("GET", f"{BASE}/conversations/c1/messages/m1", [
        FakeResponse(200, {"status": "EXECUTING_QUERY"}),
        FakeResponse(200, {"status": "COMPLETED", "attachments": [
            {"attachment_id": "a1", "query": {"query": "SELECT 1", "description": "Total"}},
            {"attachment_id": "a2", "text": {"content": "Your balance is $123.45"}}]}),
    ])
    ans = _client(fake_http).ask("What is my balance?")
    assert ans.completed and ans.conversation_id == "c1" and ans.message_id == "m1"
    assert ans.text == ["Your balance is $123.45"]
    assert ans.queries[0].sql == "SELECT 1" and ans.queries[0].rows == [["123.45"]] and ans.statement_ids == ["st1"]
    assert [s for _, s in ans.timeline] == ["EXECUTING_QUERY", "COMPLETED"]
    assert fake_http.calls[0]["json"] == {"content": "What is my balance?"}


def test_ask_follow_up_uses_conversation(fake_http):
    fake_http.route("POST", f"{BASE}/conversations/c1/messages", FakeResponse(200, {"id": "m2"}))
    fake_http.route("GET", f"{BASE}/conversations/c1/messages/m2", FakeResponse(200, {"status": "COMPLETED", "attachments": []}))
    ans = _client(fake_http).ask("and last month?", "c1")
    assert ans.message_id == "m2" and ans.queries == []


def test_ask_failed_status_carries_error(fake_http):
    fake_http.route("POST", f"{BASE}/start-conversation", FakeResponse(200, {"conversation_id": "c1", "message_id": "m1"}))
    fake_http.route("GET", f"{BASE}/conversations/c1/messages/m1", FakeResponse(200, {"status": "FAILED", "error": {"error": "boom"}}))
    ans = _client(fake_http).ask("q")
    assert ans.status == "FAILED" and not ans.completed and ans.error == "boom"


def test_ask_timeout(fake_http):
    fake_http.route("POST", f"{BASE}/start-conversation", FakeResponse(200, {"conversation_id": "c1", "message_id": "m1"}))
    fake_http.route("GET", f"{BASE}/conversations/c1/messages/m1", FakeResponse(200, {"status": "ASKING_AI"}))
    ans = _client(fake_http, timeout_s=10).ask("q")
    assert ans.status == "TIMEOUT" and ans.error


def test_delete_conversation(fake_http):
    fake_http.route("DELETE", f"{BASE}/conversations/c1", FakeResponse(200, {}))
    _client(fake_http).delete_conversation("c1")
    assert fake_http.calls[0]["method"] == "DELETE"
