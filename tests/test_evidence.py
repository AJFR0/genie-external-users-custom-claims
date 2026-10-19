from claims_kit.config import load_example
from claims_kit.evidence import scrub, trace_card
from claims_kit.personas import load_personas
from claims_kit.sql import StatementResult
from claims_kit.validate import SuiteContext


def test_scrub_replaces_known_values_uuids_and_hex_ids():
    obj = {"a": "host https://w.example.com sp 0f8e7d6c-1111-2222-3333-" + "444455556666 conv 01f1cbc30b811aa7a5191919ccbee2f4",
           "b": ["https://w.example.com"]}
    out = scrub(obj, {"https://w.example.com": "https://<workspace-host>"})
    assert out == {"a": "host https://<workspace-host> sp <id> conv <id>", "b": ["https://<workspace-host>"]}


class Runner:
    def execute(self, sql, parameters=None):
        if "my_access" in sql:
            return StatementResult("s", ["role", "scope_id"], [["sponsor", "PLAN-A"], ["participant", "P-2001"]])
        return StatementResult("s", ["n"], [["3"]])


class Provider:
    client_id = "app"

    def auth_for(self, claim):
        return lambda: {}


def test_trace_card_collects_grants_and_counts():
    ex = load_example("northwind")
    ctx = SuiteContext(example=ex, catalog="cat", host="h", warehouse_id="w", provider=Provider(), admin=None,
                       make_runner=lambda auth: Runner())
    linda = next(p for p in load_personas(ex) if p.id == "linda")
    card = trace_card(ctx, linda)
    assert card["claim"] == "pu-2001" and card["grants"]["rows"][0] == ["sponsor", "PLAN-A"]
    assert set(card["view_row_counts"]) == set(ex.portal_views) - {"my_access"} and card["view_row_counts"]["plan_roster"] == 3


def test_write_evidence_scrubs_the_catalog_name(tmp_path):
    import json
    from claims_kit.evidence import write_evidence
    from claims_kit.validate import CaseResult
    ex = load_example("northwind")
    ctx = SuiteContext(example=ex, catalog="secretcat", host="https://w.example.com", warehouse_id="wh9", provider=Provider(),
                       admin=None, make_runner=lambda auth: Runner())
    results = [CaseResult("privilege/read-base-table", "privilege", None, True, "denied",
                          "error: User does not have USE SCHEMA on Schema 'secretcat.northwind_base'")]
    paths = write_evidence(ctx, results, tmp_path)
    text = "".join(p.read_text() for p in paths)
    assert "secretcat" not in text and "<catalog>" in text and "https://w.example.com" not in text
