"""Settings for the local reference app, from environment variables or .env."""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

from claims_kit.local import LocalEnv, read_env


@dataclass(frozen=True)
class Settings:
    env: LocalEnv | None
    session_secret: str
    audit_path: Path
    redact_ids: bool


def load_settings(mapping: dict | None = None) -> Settings:
    m = read_env() if mapping is None else mapping
    return Settings(env=LocalEnv.from_mapping(m), session_secret=m.get("APP_SESSION_SECRET") or secrets.token_urlsafe(32),
                    audit_path=Path(m.get("AUDIT_LOG_PATH") or "audit/portal-audit.jsonl"),
                    redact_ids=m.get("APP_REDACT_IDS", "false").lower() == "true")
