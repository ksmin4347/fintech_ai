"""Browser-native realtime speech recognition Streamlit component."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


COMPONENT_DIR = Path(__file__).resolve().parent.parent / "components" / "realtime_speech"

_component = components.declare_component(
    "realtime_speech",
    path=str(COMPONENT_DIR),
)


def realtime_speech_to_text(
    *,
    initial_text: str = "",
    case_id: str = "",
    language: str = "ko-KR",
    autosend_interval_ms: int = 800,
    key: str | None = None,
) -> dict[str, Any] | None:
    """Return live transcript payloads emitted by the browser component."""
    return _component(
        initial_text=initial_text or "",
        case_id=case_id or "",
        language=language,
        autosend_interval_ms=max(300, int(autosend_interval_ms)),
        key=key,
        default=None,
    )
