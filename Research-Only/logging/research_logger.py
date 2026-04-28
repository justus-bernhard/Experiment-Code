"""Append-only JSONL event logging for pilot research sessions."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


class ResearchLogger:
    """Small append-only event logger.

    The logger keeps timing relative to the moment it is constructed. This
    makes derived measures independent from wall-clock changes during a session.
    """

    def __init__(self, log_dir: Path, session_id: str | None = None, condition: str | None = None) -> None:
        self.log_dir = log_dir
        self.events_path = log_dir / 'events.jsonl'
        self.session_id = session_id
        self.condition = condition
        self._start_monotonic = time.monotonic()
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def elapsed_ms(self) -> int:
        return int(round((time.monotonic() - self._start_monotonic) * 1000))

    def event(self, event_type: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        record = {
            'session_id': self.session_id,
            'condition': self.condition,
            'event_type': event_type,
            'timestamp_utc': utc_now_iso(),
            'elapsed_ms': self.elapsed_ms(),
            'payload': payload or {},
        }
        with self.events_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + '\n')
        return record


def read_events(events_path: Path) -> List[Dict[str, Any]]:
    if not events_path.exists():
        return []

    events: List[Dict[str, Any]] = []
    with events_path.open('r', encoding='utf-8') as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f'Malformed JSONL event at {events_path}:{line_number}') from exc
    return events


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write('\n')


def tail_text(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def event_payloads(events: Iterable[Dict[str, Any]], event_type: str) -> List[Dict[str, Any]]:
    return [
        event.get('payload', {})
        for event in events
        if event.get('event_type') == event_type
    ]
