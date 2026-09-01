"""Offline store-and-forward buffer: survives 4G dead zones.

Writes one JSON line per incident into a spool file. `flush()` pushes batches
to the uploader and deletes only what the server accepted.
"""
import json
import threading
from pathlib import Path


class Spool:
    def __init__(self, path: str | Path = None):
        self.path = Path(path or (Path(__file__).parent / "spool.jsonl"))
        self._lock = threading.Lock()

    def put(self, record: dict) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")

    def drain(self, limit: int = 100) -> list[dict]:
        """Pop up to `limit` records (removed from disk; caller owns retries)."""
        with self._lock:
            if not self.path.exists():
                return []
            lines = self.path.read_text(encoding="utf-8").splitlines()
            take, rest = lines[:limit], lines[limit:]
            self.path.write_text("\n".join(rest) + ("\n" if rest else ""), encoding="utf-8")
        records = []
        for line in take:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # corrupted line — drop
        return records

    def size(self) -> int:
        if not self.path.exists():
            return 0
        with self._lock:
            return sum(1 for _ in self.path.open("r", encoding="utf-8"))
