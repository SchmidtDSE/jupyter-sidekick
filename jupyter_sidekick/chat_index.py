"""Per-server index of chats, so they can be listed and resumed.

We persist only a small record per chat — its id, the harness it was bound to,
the ACP ``session_id``, the ``cwd`` it ran in, a title, and timestamps — **not**
the transcript. ACP agents persist their own sessions, so resuming is just
``load_session(session_id, cwd)`` against a fresh agent process (see
``HarnessSession.load_session``); the agent replays the conversation.

The index is a single JSON file for the whole server, written atomically. A
missing or corrupt file is treated as an empty index rather than an error.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional


class ChatIndex:
    def __init__(self, path: str) -> None:
        self.path = path
        self._records: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self._records = {r["chat_id"]: r for r in data if "chat_id" in r}
        except (OSError, ValueError, TypeError):
            self._records = {}  # missing / unreadable / corrupt → start empty

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(list(self._records.values()), handle, indent=2)
        os.replace(tmp, self.path)  # atomic on POSIX

    def record(self, chat_id: str, harness_id: str, session_id: str, cwd: str) -> Dict[str, Any]:
        """Insert or refresh the record for a (newly bound) chat. ``created_at``
        is set once; later binds with the same id just refresh the session/cwd."""
        now = time.time()
        existing = self._records.get(chat_id)
        if existing is None:
            existing = {
                "chat_id": chat_id,
                "harness_id": harness_id,
                "session_id": session_id,
                "cwd": cwd,
                "title": None,
                "created_at": now,
                "updated_at": now,
            }
            self._records[chat_id] = existing
        else:
            existing.update(
                harness_id=harness_id, session_id=session_id, cwd=cwd, updated_at=now
            )
        self._save()
        return existing

    def set_title(self, chat_id: str, title: str) -> None:
        """Set the chat's title once (the first user message); later calls and
        unknown chats are ignored."""
        record = self._records.get(chat_id)
        if record is None or record.get("title"):
            return
        record["title"] = title
        record["updated_at"] = time.time()
        self._save()

    def get(self, chat_id: str) -> Optional[Dict[str, Any]]:
        return self._records.get(chat_id)

    def list(self) -> List[Dict[str, Any]]:
        """All records, most-recently-active first."""
        return sorted(
            self._records.values(),
            key=lambda r: r.get("updated_at") or r.get("created_at") or 0,
            reverse=True,
        )
