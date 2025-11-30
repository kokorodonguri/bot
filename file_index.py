from __future__ import annotations

import json
from typing import Dict

from config import INDEX_PATH, TOKEN_PATH

IndexRecord = Dict[str, Dict]


def load_token() -> str:
    return TOKEN_PATH.read_text(encoding="utf-8").strip()


def load_index() -> IndexRecord:
    if not INDEX_PATH.exists():
        return {}
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_index(index: IndexRecord) -> None:
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
