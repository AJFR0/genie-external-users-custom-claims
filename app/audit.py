"""Per-user audit log (JSON lines).

Databricks query history attributes every query to the portal service principal, so it can't tell you which
end user asked. This log is the per-user record: join it to query history on statement_id. In production,
send these records to your logging pipeline instead of a local file.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

NEWLINE = "\n"


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, event: str, **fields) -> dict:
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **fields}
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + NEWLINE)
        return record

    def tail(self, n: int = 50) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(line) for line in lines if line.strip()]
