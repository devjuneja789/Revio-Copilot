from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_profiles(path: Path | None = None) -> dict[str, dict]:
    return json.loads((path or DATA_DIR / "business_profiles.json").read_text(encoding="utf-8"))
