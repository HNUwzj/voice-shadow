from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any


class JsonStore:
    def __init__(self, data_dir: str) -> None:
        self.base = Path(data_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        self.files = {
            "conversations": self.base / "conversations.json",
            "analyses": self.base / "analyses.json",
            "reports": self.base / "reports.json",
            "voices": self.base / "voices.json",
            "mailbox": self.base / "mailbox.json",
            "mailbox_clears": self.base / "mailbox_clears.json",
            "parent_styles": self.base / "parent_styles.json",
        }
        for file in self.files.values():
            if not file.exists():
                file.write_text("[]", encoding="utf-8")

    def _read(self, key: str) -> list[dict[str, Any]]:
        with self.lock:
            return json.loads(self.files[key].read_text(encoding="utf-8-sig"))

    def _write(self, key: str, data: list[dict[str, Any]]) -> None:
        with self.lock:
            self.files[key].write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def append(self, key: str, record: dict[str, Any]) -> None:
        data = self._read(key)
        data.append(record)
        self._write(key, data)

    def query_by_child_and_date(self, key: str, child_id: str, day: str) -> list[dict[str, Any]]:
        data = self._read(key)
        return [
            row
            for row in data
            if row.get("child_id") == child_id and row.get("timestamp", "").startswith(day)
        ]

    def conversation_tail(self, child_id: str, limit: int = 10) -> list[dict[str, Any]]:
        data = self._read("conversations")
        rows = [row for row in data if row.get("child_id") == child_id]
        return rows[-limit:]

    def list_by_child(self, key: str, child_id: str) -> list[dict[str, Any]]:
        data = self._read(key)
        rows = [row for row in data if row.get("child_id") == child_id]
        rows.sort(key=lambda row: row.get("timestamp", ""))
        return rows

    def list_all(self, key: str) -> list[dict[str, Any]]:
        return self._read(key)

    def clear(self, key: str) -> None:
        self._write(key, [])

    def mailbox_clear_timestamp(self, child_id: str, viewer: str) -> str:
        data = self._read("mailbox_clears")
        rows = [
            row
            for row in data
            if row.get("child_id") == child_id and row.get("viewer") == viewer
        ]
        rows.sort(key=lambda row: row.get("timestamp", ""))
        return str(rows[-1].get("timestamp", "")) if rows else ""

    def set_mailbox_clear(self, child_id: str, viewer: str) -> str:
        timestamp = self.now_iso()
        data = self._read("mailbox_clears")
        next_data = [
            row
            for row in data
            if not (row.get("child_id") == child_id and row.get("viewer") == viewer)
        ]
        next_data.append({"child_id": child_id, "viewer": viewer, "timestamp": timestamp})
        self._write("mailbox_clears", next_data)
        return timestamp

    def get_parent_style(self, child_id: str) -> dict[str, Any] | None:
        data = self._read("parent_styles")
        rows = [row for row in data if row.get("child_id") == child_id]
        rows.sort(key=lambda row: row.get("timestamp", ""))
        return rows[-1] if rows else None

    def set_parent_style(self, child_id: str, use_default: bool, custom_rules: str) -> dict[str, Any]:
        data = self._read("parent_styles")
        next_data = [row for row in data if row.get("child_id") != child_id]
        record = {
            "child_id": child_id,
            "use_default": use_default,
            "custom_rules": custom_rules,
            "timestamp": self.now_iso(),
        }
        next_data.append(record)
        self._write("parent_styles", next_data)
        return record

    def latest_voice(self, child_id: str) -> dict[str, Any] | None:
        data = self._read("voices")
        rows = [row for row in data if row.get("child_id") == child_id]
        return rows[-1] if rows else None

    def list_voices(self, child_id: str) -> list[dict[str, Any]]:
        data = self._read("voices")
        rows = [row for row in data if row.get("child_id") == child_id]
        rows.sort(key=lambda row: row.get("timestamp", ""), reverse=True)
        return rows

    def delete_voice(self, child_id: str, voice_id: str) -> bool:
        data = self._read("voices")
        next_data: list[dict[str, Any]] = []
        deleted = False
        for row in data:
            same_child = row.get("child_id") == child_id
            same_voice = str(row.get("voice_id", "")).strip() == voice_id
            if same_child and same_voice:
                deleted = True
                continue
            next_data.append(row)

        if deleted:
            self._write("voices", next_data)
        return deleted

    @staticmethod
    def now_iso() -> str:
        return datetime.now().isoformat(timespec="seconds")
