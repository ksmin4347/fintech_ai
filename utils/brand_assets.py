"""Brand asset helpers."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"


@lru_cache(maxsize=8)
def brand_logo_data_uri(name: str = "fincoc_logo_mark.png") -> str:
    path = ASSET_DIR / name
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"
