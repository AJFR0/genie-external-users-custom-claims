"""Server-side map of (example, portal user) to Genie conversation id.

Genie conversations belong to the service principal, and any token from that service principal can read them.
So the backend owns the mapping: the browser never sees, sends or chooses a conversation id.
"""
from __future__ import annotations

import threading


class ConversationStore:
    def __init__(self):
        self._map: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()

    def get(self, example: str, portal_user_id: str) -> str | None:
        with self._lock:
            return self._map.get((example, portal_user_id))

    def set(self, example: str, portal_user_id: str, conversation_id: str) -> None:
        with self._lock:
            self._map[(example, portal_user_id)] = conversation_id

    def pop(self, example: str, portal_user_id: str) -> str | None:
        with self._lock:
            return self._map.pop((example, portal_user_id), None)
