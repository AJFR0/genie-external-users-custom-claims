"""Account groups and governed tags for layered enforcement, through the workspace's account proxies.

A workspace admin can create account groups through the workspace host (/api/2.0/account/scim/v2). Workspace-local
groups would not work: Unity Catalog grants and policies need account groups. `do` is WorkspaceClient().api_client.do.
"""
from __future__ import annotations

from .tags import TagSet

SCIM = "/api/2.0/account/scim/v2/Groups"
TAG_POLICIES = "/api/2.1/tag-policies"


def _find_group(do, name: str) -> str | None:
    found = do("GET", SCIM, query={"filter": f'displayName eq "{name}"'}).get("Resources") or []
    return found[0]["id"] if found else None


def _create_group(do, name: str) -> str:
    return do("POST", SCIM, body={"schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"], "displayName": name})["id"]


def ensure_account_group(do, name: str) -> str:
    return _find_group(do, name) or _create_group(do, name)


def ensure_group_member(do, group_id: str, member_id: str) -> None:
    do("PATCH", f"{SCIM}/{group_id}", body={
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [{"op": "add", "path": "members", "value": [{"value": member_id}]}]})


def add_portal_member(do, group_name: str, member_id: str) -> str:
    """Make sure the group exists and has the member. Returns the group id.

    The SCIM list can briefly return a group that was just deleted. Adding a member to it then fails with
    "not found", so the group is created again once.
    """
    gid = ensure_account_group(do, group_name)
    try:
        ensure_group_member(do, gid, member_id)
    except Exception as exc:
        if "NOT FOUND" not in str(exc).upper():
            raise
        gid = _create_group(do, group_name)
        ensure_group_member(do, gid, member_id)
    return gid


def delete_account_group(do, name: str) -> bool:
    gid = _find_group(do, name)
    if gid:
        do("DELETE", f"{SCIM}/{gid}")
    return bool(gid)


def _wanted(tags: TagSet) -> dict:
    wanted: dict = {}
    for t in (*tags.grains.values(), *tags.keys.values()):
        wanted.setdefault(t.key, set()).add(t.value)
    return wanted


def require_governed_tags(do, tags: TagSet) -> list[str]:
    """Policies match governed tags only. A same-named free-form tag would leave the policies matching nothing."""
    if tags.name != "governed":
        return []
    problems = []
    for key, values in sorted(_wanted(tags).items()):
        try:
            have = {v.get("name") for v in do("GET", f"{TAG_POLICIES}/{key}").get("values") or []}
        except Exception:
            problems.append(f"{key} is not a governed tag in this account")
            continue
        missing = sorted(values - have)
        if missing:
            problems.append(f"governed tag {key} lacks allowed values {missing}")
    return problems


def create_governed_tags(do, tags: TagSet) -> list[str]:
    log = []
    for key, values in sorted(_wanted(tags).items()):
        try:
            do("POST", TAG_POLICIES, body={"tag_key": key, "values": [{"name": v} for v in sorted(values)],
                                           "description": "Portal row policies (layered enforcement). Assign through governance only."})
            log.append(f"created governed tag {key} with values {sorted(values)}")
        except Exception as exc:
            if "ALREADY_EXISTS" in str(exc).upper():
                log.append(f"governed tag {key} already exists")
            else:
                log.append(f"could not create governed tag {key} ({str(exc)[:80]}). Ask an account admin to create it "
                           f"with values {sorted(values)} (Admin Runbook, step 1), or deploy with --var tag_set=stand_in "
                           f"for evaluation.")
    return log
