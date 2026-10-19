from app_fakes import FakeRunner, make_client
from claims_kit.sql import StatementError, StatementResult

GRANT = {"portal_user_id": "pu-1003", "role": "participant", "scope_type": "participant", "scope_id": "P-0003"}


def affected(n):
    return StatementResult("s", ["num_affected_rows"], [[str(n)]])


def test_admin_requires_profile(tmp_path):
    client, *_ = make_client(tmp_path, admin=None)
    assert client.get("/admin/api/northwind/grants").status_code == 503
    assert "ADMIN_PROFILE" in client.get("/admin").text


def test_list_grants_reads_governance_table(tmp_path):
    admin = FakeRunner(result=StatementResult("s", ["portal_user_id"], [["pu-1001"]]))
    client, *_ = make_client(tmp_path, admin=admin)
    assert client.get("/admin/api/northwind/grants").json()["rows"] == [["pu-1001"]]
    assert "`cat`.`northwind_governance`.`portal_user_grants`" in admin.calls[0][0]


def test_add_grant_rejects_malformed_claim(tmp_path):
    admin = FakeRunner()
    client, *_ = make_client(tmp_path, admin=admin)
    r = client.post("/admin/api/northwind/grants", json={**GRANT, "portal_user_id": " PU-1003 "})
    assert r.status_code == 400 and admin.calls == []


def test_add_grant_rejects_unknown_role(tmp_path):
    client, *_ = make_client(tmp_path, admin=FakeRunner())
    assert client.post("/admin/api/northwind/grants", json={**GRANT, "role": "superuser"}).status_code == 400


def test_add_grant_inserts_with_parameters_and_audits(tmp_path):
    admin = FakeRunner(result=affected(1))
    client, services, *_ = make_client(tmp_path, admin=admin)
    assert client.post("/admin/api/northwind/grants", json={**GRANT, "valid_to": "2026-12-31"}).status_code == 200
    sql, params = admin.calls[0]
    assert sql.startswith("INSERT INTO `cat`.`northwind_governance`.`portal_user_grants`") and ":uid" in sql
    assert params["uid"] == "pu-1003" and str(params["vto"]) == "2026-12-31"
    assert services.audit.tail()[-1]["event"] == "grant_added"


def test_expire_conflict_when_nothing_matches(tmp_path):
    client, *_ = make_client(tmp_path, admin=FakeRunner(result=affected(0)))
    assert client.post("/admin/api/northwind/grants/expire", json=GRANT).status_code == 409


def test_delete_grant(tmp_path):
    admin = FakeRunner(result=affected(1))
    client, *_ = make_client(tmp_path, admin=admin)
    assert client.request("DELETE", "/admin/api/northwind/grants", json=GRANT).status_code == 200
    assert admin.calls[0][0].startswith("DELETE FROM")


def test_policy_update_validates_field_and_type(tmp_path):
    admin = FakeRunner(result=affected(1))
    client, *_ = make_client(tmp_path, admin=admin)
    assert client.put("/admin/api/northwind/role-policies/advisor", json={"field": "role", "value": True}).status_code == 400
    assert client.put("/admin/api/northwind/role-policies/advisor", json={"field": "mask_dob", "value": 3}).status_code == 400
    assert client.put("/admin/api/northwind/role-policies/advisor", json={"field": "mask_dob", "value": False}).status_code == 200
    assert "SET `mask_dob` = :value" in admin.calls[-1][0] and admin.calls[-1][1] == {"value": False, "role": "advisor"}


def test_constraint_violation_becomes_400(tmp_path):
    err = StatementError("[DELTA_VIOLATE_CONSTRAINT_WITH_VALUES] CHECK constraint known_scope violated")
    client, *_ = make_client(tmp_path, admin=FakeRunner(error=err))
    r = client.post("/admin/api/northwind/grants", json=GRANT)
    assert r.status_code == 400 and "known_scope" in r.json()["detail"]


def test_redact_mode_scrubs_admin_errors(tmp_path):
    uuid = "0f8e7d6c-1111-2222-3333-" + "444455556666"
    err = StatementError(f"[INSUFFICIENT_PERMISSIONS] on https://host.example for {uuid}")
    client, *_ = make_client(tmp_path, admin=FakeRunner(error=err), redact_ids=True, host="https://host.example")
    detail = client.get("/admin/api/northwind/grants").json()["detail"]
    assert "host.example" not in detail and uuid not in detail and "INSUFFICIENT_PERMISSIONS" in detail
