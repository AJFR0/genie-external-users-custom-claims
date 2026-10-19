import json

from claims_kit.genie_space import build_serialized_space, grant_can_run, space_title, stable_id, upsert_space

SPEC = {
    "title": "Portal assistant",
    "description": "d",
    "instructions": "First rule.\n\nSecond rule.",
    "sample_questions": ["What is my balance?", "What can I see?"],
    "tables": [{"view": "portal.my_accounts"}, {"view": "portal.fund_lineup", "prompt_matching": True}],
}
IDS = {"portal.my_accounts": "c.p.my_accounts", "portal.fund_lineup": "c.p.fund_lineup"}
COLS = {"portal.my_accounts": ["plan_id", "balance"], "portal.fund_lineup": ["fund_name"]}


def test_build_serialized_space_sorts_and_sets_prompt_matching():
    space = json.loads(build_serialized_space(SPEC, table_ids=IDS, columns=COLS))
    assert space["version"] == 2
    tables = space["data_sources"]["tables"]
    assert [t["identifier"] for t in tables] == ["c.p.fund_lineup", "c.p.my_accounts"]
    acct = tables[1]["column_configs"]
    assert [c["column_name"] for c in acct] == ["balance", "plan_id"]
    assert all(c["enable_format_assistance"] is False and c["enable_entity_matching"] is False for c in acct)
    assert tables[0]["column_configs"][0]["enable_entity_matching"] is True
    ids = [q["id"] for q in space["config"]["sample_questions"]]
    assert ids == sorted(ids) and all(len(i) == 32 for i in ids)
    assert space["instructions"]["text_instructions"][0]["content"] == ["First rule.\n", "Second rule.\n"]


def test_stable_id_and_title():
    assert stable_id("x") == stable_id("x") and len(stable_id("x")) == 32
    assert space_title(SPEC, "genie_claims_ref") == "Portal assistant [genie_claims_ref]"


class FakeDo:
    def __init__(self, spaces):
        self.spaces = spaces
        self.calls = []

    def __call__(self, method, path, query=None, body=None):
        self.calls.append((method, path, query, body))
        if method == "GET":
            return {"spaces": self.spaces}
        if method == "POST":
            return {"space_id": "new1"}
        return {}


def test_upsert_creates_when_missing():
    do = FakeDo([{"space_id": "x", "title": "other"}])
    assert upsert_space(do, title="T", description="d", warehouse_id="w", parent_path="/Users/me", serialized_space="{}") == ("new1", "created")
    assert do.calls[-1][0] == "POST" and do.calls[-1][3]["parent_path"] == "/Users/me"


def test_upsert_updates_by_title():
    do = FakeDo([{"space_id": "s7", "title": "T"}])
    assert upsert_space(do, title="T", description="d", warehouse_id="w", parent_path="/p", serialized_space="{}") == ("s7", "updated")
    assert do.calls[-1][:2] == ("PATCH", "/api/2.0/genie/spaces/s7")


def test_grant_can_run():
    do = FakeDo([])
    grant_can_run(do, "s7", "app-id")
    assert do.calls[0] == ("PATCH", "/api/2.0/permissions/genie/s7", None,
                           {"access_control_list": [{"service_principal_name": "app-id", "permission_level": "CAN_RUN"}]})
