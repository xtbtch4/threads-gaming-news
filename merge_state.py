from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path) -> dict:
    if not path.exists():
        return {"items": [], "updated_at": None}
    return json.loads(path.read_text(encoding="utf-8"))


def richness(item: dict) -> tuple[int, int, str]:
    return (
        1 if item.get("threads_id") else 0,
        1 if item.get("telegram_message_id") else 0,
        str(item.get("threads_published_at") or item.get("telegram_published_at") or ""),
    )


def merge(remote: dict, local: dict) -> dict:
    merged: dict[str, dict] = {}
    for item in list(remote.get("items", [])) + list(local.get("items", [])):
        key = str(item.get("fingerprint") or item.get("url") or item.get("title") or "")
        if not key:
            continue
        current = merged.get(key)
        if current is None or richness(item) >= richness(current):
            merged[key] = item
    items = sorted(
        merged.values(),
        key=lambda x: str(x.get("telegram_published_at") or x.get("published_at_source") or ""),
    )[-1200:]
    return {"items": items, "updated_at": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: merge_state.py REMOTE LOCAL OUTPUT")
    remote_path, local_path, output_path = map(Path, sys.argv[1:])
    output_path.write_text(
        json.dumps(merge(load(remote_path), load(local_path)), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
