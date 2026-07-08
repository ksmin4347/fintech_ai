"""Policy document loader."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import requests

from models.rag_schemas import PolicyDocument

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}


class PolicyDocumentLoadError(RuntimeError):
    pass


def _use_supabase() -> bool:
    return os.getenv("POLICY_DATA_SOURCE", "").strip().lower() == "supabase"


def _supabase_config() -> tuple[str, str, str]:
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    table = (
        os.getenv("SUPABASE_POLICY_DOCUMENT_TABLE")
        or os.getenv("SUPABASE_POLICY_TABLE")
        or "announcements"
    ).strip()
    if not url:
        raise PolicyDocumentLoadError("SUPABASE_URL is missing.")
    if not key:
        raise PolicyDocumentLoadError("SUPABASE_KEY or SUPABASE_ANON_KEY is missing.")
    if not table:
        raise PolicyDocumentLoadError("Supabase policy document table is missing.")
    return url, key, table


def _supabase_select(table: str, *, limit: int = 5000) -> list[dict[str, Any]]:
    url, key, _ = _supabase_config()
    response = requests.get(
        f"{url}/rest/v1/{table}",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "count=exact",
        },
        params={"select": "*", "limit": str(limit)},
        timeout=30,
    )
    if response.status_code >= 400:
        raise PolicyDocumentLoadError(
            f"Supabase policy document load failed ({table}, HTTP {response.status_code}): "
            f"{response.text[:500]}"
        )
    data = response.json()
    if not isinstance(data, list):
        raise PolicyDocumentLoadError(f"Supabase policy document table returned non-list data: {table}")
    return data


def _first(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def _as_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _row_to_raw_text(row: dict[str, Any]) -> str:
    direct = _first(
        row,
        "raw_text",
        "content",
        "text",
        "parsed_text",
        "full_text",
        "body",
        "summary_text",
        "description",
        "target_description",
        "announcement_summary",
        default="",
    )
    useful_parts = []
    if direct:
        useful_parts.append(_as_text(direct))
    for key in (
        "announcement_name",
        "policy_name",
        "program_name",
        "title",
        "summary_text",
        "summary",
        "institution",
        "agency",
        "apply_period_raw",
        "apply_method_raw",
        "apply_url",
        "detail_url",
        "contact_info",
        "source_url",
        "application_start_date",
        "application_end_date",
        "registered_at",
        "fetched_at",
    ):
        value = row.get(key)
        if value not in (None, ""):
            useful_parts.append(f"{key}: {_as_text(value)}")
    return "\n".join(useful_parts)


def _to_policy_document(row: dict[str, Any], index: int, table: str) -> PolicyDocument:
    doc_id = str(_first(row, "doc_id", "document_id", "announcement_id", "policy_id", "id", default=f"supabase-doc-{index}"))
    title = str(
        _first(
            row,
            "title",
            "announcement_name",
            "policy_name",
            "program_name",
            "name",
            default=doc_id,
        )
    )
    institution = _first(
        row,
        "institution",
        "agency",
        "agency_name",
        "organization",
        "organization_name",
        "department",
        "ministry",
        "provider",
        "source_name",
    )
    source_name = _first(row, "source_name", "announcement_name", "title", default=title)
    source_url = _first(row, "source_url", "announcement_url", "detail_url", "apply_url", "url", "link")
    source_date = _first(row, "source_date", "announcement_date", "registered_at", "published_at", "created_at", "fetched_at")
    return PolicyDocument(
        doc_id=doc_id,
        title=title,
        institution=str(institution) if institution not in (None, "") else None,
        file_path=f"supabase://{table}/{doc_id}",
        source_name=str(source_name) if source_name not in (None, "") else None,
        source_url=str(source_url) if source_url not in (None, "") else None,
        source_date=str(source_date)[:10] if source_date not in (None, "") else None,
        is_sample_data=bool(row.get("is_sample_data", False)),
        raw_text=_row_to_raw_text(row),
    )


def load_policy_documents_from_supabase() -> list[PolicyDocument]:
    _, _, table = _supabase_config()
    rows = _supabase_select(table)
    active_rows = [
        row for row in rows
        if row.get("is_active", True) is not False and row.get("deleted_at") in (None, "")
    ]
    return [
        doc for idx, row in enumerate(active_rows, 1)
        if (doc := _to_policy_document(row, idx, table)).raw_text.strip()
    ]


def load_markdown_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception as e:
        return f"[file read error: {e}]"


def load_pdf_file(path: str) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        pages = [p.extract_text() or "" for p in reader.pages]
        return "\n".join(pages)
    except ImportError:
        return "[pypdf package is required to parse PDFs]"
    except Exception as e:
        return f"[PDF parse error: {e}]"


def _extract_metadata(text: str, filename: str) -> dict:
    meta: dict = {"title": filename, "institution": None, "source_name": None, "source_url": None, "source_date": None}
    title_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if title_m:
        meta["title"] = title_m.group(1).strip()
    for pattern, key in [
        (r"\*\*기관명:\*\*\s*(.+)", "institution"),
        (r"\*\*출처명:\*\*\s*(.+)", "source_name"),
        (r"\*\*출처 URL:\*\*\s*(.+)", "source_url"),
        (r"\*\*기준일:\*\*\s*(.+)", "source_date"),
    ]:
        m = re.search(pattern, text)
        if m:
            meta[key] = m.group(1).strip()
    return meta


def _load_local_policy_documents(directory: str) -> list[PolicyDocument]:
    docs: list[PolicyDocument] = []
    dir_path = Path(directory)
    if not dir_path.exists():
        return docs

    for fp in sorted(dir_path.iterdir()):
        if fp.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if fp.suffix.lower() == ".pdf":
            raw = load_pdf_file(str(fp))
        else:
            raw = load_markdown_file(str(fp))

        meta = _extract_metadata(raw, fp.stem)
        docs.append(
            PolicyDocument(
                doc_id=fp.stem,
                title=meta["title"],
                institution=meta.get("institution"),
                file_path=str(fp),
                source_name=meta.get("source_name"),
                source_url=meta.get("source_url"),
                source_date=meta.get("source_date"),
                is_sample_data=True,
                raw_text=raw,
            )
        )
    return docs


def load_policy_documents(directory: str) -> list[PolicyDocument]:
    if _use_supabase() and Path(directory).name == "policy_docs":
        return load_policy_documents_from_supabase()
    return _load_local_policy_documents(directory)
