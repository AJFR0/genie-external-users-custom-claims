from app.audit import AuditLog
from app.conversations import ConversationStore
from app.settings import load_settings


def test_conversation_store_is_keyed_by_example_and_user():
    store = ConversationStore()
    store.set("northwind", "pu-1001", "c1")
    assert store.get("northwind", "pu-1001") == "c1" and store.get("northwind", "pu-1002") is None
    assert store.pop("northwind", "pu-1001") == "c1" and store.get("northwind", "pu-1001") is None


def test_audit_log_appends_and_tails(tmp_path):
    log = AuditLog(tmp_path / "x" / "audit.jsonl")
    log.write("sign_in", portal_user_id="pu-1001")
    rec = log.write("ask", portal_user_id="pu-1001", statement_ids=["s1"])
    assert rec["event"] == "ask" and "ts" in rec
    assert [r["event"] for r in log.tail(10)] == ["sign_in", "ask"]


def test_load_settings_from_mapping():
    s = load_settings({"DATABRICKS_HOST": "https://h", "WAREHOUSE_ID": "w", "APP_REDACT_IDS": "true"})
    assert s.redact_ids and s.env.host == "https://h" and s.session_secret
