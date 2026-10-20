from claims_kit.identity import (SCIM, TAG_POLICIES, add_portal_member, create_governed_tags, delete_account_group,
                                 ensure_account_group, ensure_group_member, require_governed_tags)
from claims_kit.tags import load_tag_set


class FakeDo:
    def __init__(self, responses=None, fail=None):
        self.calls, self.responses, self.fail = [], dict(responses or {}), dict(fail or {})

    def __call__(self, method, path, query=None, body=None):
        self.calls.append((method, path, query, body))
        err = self.fail.get((method, path))
        if isinstance(err, list):
            if err:
                raise err.pop(0)
        elif err is not None:
            raise err
        resp = self.responses.get((method, path), {})
        return resp.pop(0) if isinstance(resp, list) else resp


def test_existing_group_is_reused():
    do = FakeDo({("GET", SCIM): {"Resources": [{"id": "g1", "displayName": "grp"}]}})
    assert ensure_account_group(do, "grp") == "g1"
    assert [c[0] for c in do.calls] == ["GET"] and do.calls[0][2] == {"filter": 'displayName eq "grp"'}


def test_missing_group_is_created_as_an_account_group():
    do = FakeDo({("GET", SCIM): {"Resources": []}, ("POST", SCIM): {"id": "g2"}})
    assert ensure_account_group(do, "grp") == "g2"
    assert do.calls[1][3]["displayName"] == "grp"
    assert do.calls[1][3]["schemas"] == ["urn:ietf:params:scim:schemas:core:2.0:Group"]


def test_member_is_added_with_a_scim_patch():
    do = FakeDo()
    ensure_group_member(do, "g1", "sp-id")
    method, path, _, body = do.calls[0]
    assert (method, path) == ("PATCH", f"{SCIM}/g1")
    assert body["Operations"] == [{"op": "add", "path": "members", "value": [{"value": "sp-id"}]}]


def test_a_stale_group_from_the_list_is_recreated_once():
    """The SCIM list can still return a group that was just deleted; adding a member to it then fails."""
    do = FakeDo({("GET", SCIM): {"Resources": [{"id": "gone"}]}, ("POST", SCIM): {"id": "fresh"}},
                fail={("PATCH", f"{SCIM}/gone"): RuntimeError("invalidValue Group with id gone not found")})
    assert add_portal_member(do, "grp", "sp-id") == "fresh"
    assert ("PATCH", f"{SCIM}/fresh") in [(c[0], c[1]) for c in do.calls]


def test_delete_group_reports_absent():
    assert delete_account_group(FakeDo({("GET", SCIM): {"Resources": []}}), "grp") is False
    do = FakeDo({("GET", SCIM): {"Resources": [{"id": "g1"}]}})
    assert delete_account_group(do, "grp") is True and do.calls[-1][:2] == ("DELETE", f"{SCIM}/g1")


def test_require_governed_tags_flags_missing_tags_and_missing_values():
    tags = load_tag_set("governed")
    do = FakeDo({("GET", f"{TAG_POLICIES}/portal_grain"): {"tag_key": "portal_grain", "values": [{"name": "accounts"}]}},
                fail={("GET", f"{TAG_POLICIES}/portal_key"): RuntimeError("RESOURCE_DOES_NOT_EXIST")})
    problems = require_governed_tags(do, tags)
    assert any("portal_key" in p and "not a governed tag" in p for p in problems)
    assert any("portal_grain" in p and "roster" in p for p in problems)


def test_require_governed_tags_passes_when_every_value_exists():
    tags = load_tag_set("governed")
    grains = [{"name": g} for g in tags.grains]
    keys = [{"name": k} for k in tags.keys]
    do = FakeDo({("GET", f"{TAG_POLICIES}/portal_grain"): {"values": grains},
                 ("GET", f"{TAG_POLICIES}/portal_key"): {"values": keys}})
    assert require_governed_tags(do, tags) == []


def test_require_governed_tags_skips_the_stand_in_set():
    do = FakeDo()
    assert require_governed_tags(do, load_tag_set("stand_in")) == [] and do.calls == []


def test_create_governed_tags_sends_the_allowed_values():
    do = FakeDo()
    create_governed_tags(do, load_tag_set("governed"))
    bodies = {c[3]["tag_key"]: c[3] for c in do.calls if c[:2] == ("POST", TAG_POLICIES)}
    assert set(bodies) == {"portal_grain", "portal_key"}
    assert {v["name"] for v in bodies["portal_key"]["values"]} == {"member", "tenant", "pharmacy", "cell_count"}


def test_create_governed_tags_prints_instructions_when_denied():
    do = FakeDo(fail={("POST", TAG_POLICIES): RuntimeError("PERMISSION_DENIED")})
    log = create_governed_tags(do, load_tag_set("governed"))
    assert any("account admin" in line.lower() for line in log)
