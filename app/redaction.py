"""Screen-sharing mode: hide the workspace host, warehouse, service principal ids, any UUID or 32-hex id, and the catalog."""
from __future__ import annotations

from urllib.parse import urlparse

from claims_kit.trace import replace_identifier, scrub


def screen_safe(obj, settings, catalog: str | None, *ids: str):
    secrets = {i: "<id>" for i in ids if i}
    env = settings.env
    if env is not None:
        secrets[env.host] = "https://<workspace-host>"
        netloc = urlparse(env.host).netloc
        if netloc:
            secrets[netloc] = "<workspace-host>"
        secrets[env.warehouse_id] = "<warehouse-id>"
    out = scrub(obj, secrets)
    return replace_identifier(out, catalog, "<catalog>") if catalog else out
