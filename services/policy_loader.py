"""Policy data loader."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from models.schemas import PolicyProduct

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LIST_FIELDS = {
    "allowed_industries",
    "excluded_industries",
    "allowed_regions",
    "allowed_business_types",
    "funding_purposes",
    "required_documents",
    "exclusion_conditions",
    "rule_limitations",
}
REGION_HINTS = [
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시",
    "경기도", "강원특별자치도", "충청북도", "충청남도", "전북특별자치도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도",
]
FUNDING_PURPOSE_HINTS = {
    "창업": "창업자금",
    "경영안정": "운영자금",
    "운영": "운영자금",
    "시설": "시설자금",
    "설비": "시설자금",
    "보증": "보증",
    "특례보증": "보증",
    "이차보전": "이차보전",
    "융자": "정책자금",
    "대출": "정책자금",
}


class PolicyDataLoadError(RuntimeError):
    pass


def get_policies_path() -> Path:
    return DATA_DIR / "policies_sample.json"


def _use_supabase() -> bool:
    return os.getenv("POLICY_DATA_SOURCE", "").strip().lower() == "supabase"


def _supabase_config() -> tuple[str, str, str]:
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "").strip()
    table = (os.getenv("SUPABASE_POLICY_TABLE") or "announcements").strip()
    if not url:
        raise PolicyDataLoadError("SUPABASE_URL is missing.")
    if not key:
        raise PolicyDataLoadError("SUPABASE_KEY or SUPABASE_ANON_KEY is missing.")
    if not table:
        raise PolicyDataLoadError("SUPABASE_POLICY_TABLE is missing.")
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
        raise PolicyDataLoadError(
            f"Supabase policy table load failed ({table}, HTTP {response.status_code}): "
            f"{response.text[:500]}"
        )
    data = response.json()
    if not isinstance(data, list):
        raise PolicyDataLoadError(f"Supabase policy table returned non-list data: {table}")
    return data


def _first(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def _merge_nested_policy_data(row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(row)
    for key in (
        "policy_data",
        "program_data",
        "structured_data",
        "parsed_data",
        "extracted_fields",
        "eligibility_rules",
        "rules",
    ):
        value = row.get(key)
        parsed: Any = value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
        if isinstance(parsed, dict):
            for nested_key, nested_value in parsed.items():
                if merged.get(nested_key) in (None, ""):
                    merged[nested_key] = nested_value
    return merged


def _as_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [str(v).strip() for v in value.values() if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            return _as_list(json.loads(text))
        except json.JSONDecodeError:
            pass
    return [part.strip() for part in re.split(r"[;\n,]", text) if part.strip()]


def _as_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    digits = re.sub(r"[^0-9-]", "", str(value))
    if digits in ("", "-"):
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _as_date_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)[:10]


def _combined_text(row: dict[str, Any]) -> str:
    parts = [
        _first(row, "announcement_name", "policy_name", "program_name", "title", default=""),
        _first(row, "summary_text", "summary", "description", "announcement_summary", "target_description", default=""),
        _first(row, "apply_period_raw", "application_period", default=""),
        _first(row, "apply_method_raw", "application_method", default=""),
        _first(row, "contact_info", "contact", default=""),
    ]
    return "\n".join(str(part) for part in parts if part not in (None, ""))


def _infer_regions(text: str) -> list[str]:
    regions = []
    for region in REGION_HINTS:
        if region in text and region not in regions:
            regions.append(region)
    return regions


def _infer_policy_type(text: str) -> str:
    if "특례보증" in text or "보증" in text:
        return "보증"
    if "이차보전" in text or "이자지원" in text:
        return "이차보전"
    if "융자" in text or "대출" in text:
        return "대출"
    if "자금" in text:
        return "정책자금"
    return "공고"


def _infer_funding_purposes(text: str) -> list[str]:
    purposes = []
    for keyword, purpose in FUNDING_PURPOSE_HINTS.items():
        if keyword in text and purpose not in purposes:
            purposes.append(purpose)
    return purposes


def _infer_business_types(text: str) -> list[str]:
    business_types = []
    for keyword in ("소상공인", "중소기업", "소기업", "창업기업", "청년 창업기업"):
        if keyword in text and keyword not in business_types:
            business_types.append(keyword)
    return business_types


def _infer_max_amount(text: str) -> int | None:
    amount_pattern = re.compile(r"(?:최대|한도|업체당|기업당|지원)\s*([0-9,.]+)\s*(억원|억|백만원|천만원|만원|원)")
    multipliers = {
        "억원": 100_000_000,
        "억": 100_000_000,
        "백만원": 1_000_000,
        "천만원": 10_000_000,
        "만원": 10_000,
        "원": 1,
    }
    amounts = []
    for number, unit in amount_pattern.findall(text):
        try:
            amounts.append(int(float(number.replace(",", "")) * multipliers[unit]))
        except ValueError:
            continue
    if amounts:
        return max(amounts)

    fallback_pattern = re.compile(r"([0-9,.]+)\s*(억원|억|백만원|천만원|만원|원)")
    for number, unit in fallback_pattern.findall(text):
        try:
            amounts.append(int(float(number.replace(",", "")) * multipliers[unit]))
        except ValueError:
            continue
    return max(amounts) if amounts else None


def _infer_institution(row: dict[str, Any], fallback: str = "공고문 참조") -> str:
    direct = _first(
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
    if direct not in (None, ""):
        return str(direct)
    contact = str(row.get("contact_info") or "").strip()
    if contact:
        first_line = contact.splitlines()[0]
        first_line = re.sub(r"\d{2,4}-\d{3,4}-\d{4}.*$", "", first_line).strip(" /,")
        if first_line:
            return first_line
    return fallback


def _build_notes(row: dict[str, Any]) -> str:
    notes = []
    for label, key in (
        ("신청기간", "apply_period_raw"),
        ("신청방법", "apply_method_raw"),
        ("문의처", "contact_info"),
    ):
        value = row.get(key)
        if value not in (None, ""):
            notes.append(f"{label}: {value}")
    existing = _first(row, "notes", "memo", default="")
    if existing:
        notes.append(str(existing))
    return "\n".join(notes)


def _to_policy_product(row: dict[str, Any], index: int) -> PolicyProduct:
    row = _merge_nested_policy_data(row)
    text = _combined_text(row)
    policy_id = str(_first(row, "policy_id", "announcement_id", "id", "program_id", default=f"supabase-{index}"))
    policy_name = str(
        _first(
            row,
            "policy_name",
            "program_name",
            "support_program_name",
            "announcement_name",
            "title",
            "name",
            default=policy_id,
        )
    )
    institution = _infer_institution(row)
    policy_type = str(
        _first(row, "policy_type", "support_type", "program_type", "category", "type", default=_infer_policy_type(text))
    )
    source_name = str(_first(row, "source_name", "announcement_name", "title", default=policy_name))
    source_url = str(_first(row, "source_url", "announcement_url", "detail_url", "apply_url", "url", "link", default="") or "")
    source_date = _as_date_text(
        _first(row, "source_date", "announcement_date", "registered_at", "published_at", "created_at", "fetched_at")
    ) or ""

    item = {
        "policy_id": policy_id,
        "policy_name": policy_name,
        "institution": institution,
        "policy_type": policy_type,
        "target_description": str(
            _first(
                row,
                "target_description",
                "target",
                "summary_text",
                "summary",
                "description",
                "announcement_summary",
                default="",
            )
            or ""
        ),
        "allowed_industries": _as_list(
            _first(row, "allowed_industries", "industries", "target_industries", "business_sectors", "sectors")
        ),
        "excluded_industries": _as_list(_first(row, "excluded_industries", "excluded_sectors", "excluded_businesses")),
        "allowed_regions": _as_list(_first(row, "allowed_regions", "regions", "target_regions", "region", "location"))
        or _infer_regions(text),
        "allowed_business_types": _as_list(
            _first(row, "allowed_business_types", "business_types", "target_business_types")
        ) or _infer_business_types(text),
        "min_business_months": _as_int(
            _first(row, "min_business_months", "business_months_min", "min_months", "min_operating_months")
        ),
        "max_business_months": _as_int(
            _first(row, "max_business_months", "business_months_max", "max_months", "max_operating_months")
        ),
        "min_revenue": _as_int(_first(row, "min_revenue", "revenue_min", "min_sales", "min_annual_revenue")),
        "max_revenue": _as_int(_first(row, "max_revenue", "revenue_max", "max_sales", "max_annual_revenue")),
        "credit_score_min": _as_int(_first(row, "credit_score_min", "min_credit_score", "credit_min")),
        "credit_score_max": _as_int(_first(row, "credit_score_max", "max_credit_score", "credit_max")),
        "funding_purposes": _as_list(_first(row, "funding_purposes", "funding_purpose", "purposes", "use_of_funds"))
        or _infer_funding_purposes(text),
        "max_amount": _as_int(_first(row, "max_amount", "support_amount", "max_support_amount", "loan_limit", "limit_amount"))
        or _infer_max_amount(text),
        "interest_or_fee_description": str(
            _first(row, "interest_or_fee_description", "interest_rate", "rate_info", "fee_info", default="") or ""
        ),
        "guarantee_description": str(
            _first(row, "guarantee_description", "guarantee_info", "collateral_info", default="") or ""
        ),
        "application_start_date": _as_date_text(
            _first(row, "application_start_date", "apply_start_date", "start_date", "reception_start_date")
        ),
        "application_end_date": _as_date_text(
            _first(row, "application_end_date", "apply_end_date", "end_date", "reception_end_date")
        ),
        "required_documents": _as_list(_first(row, "required_documents", "documents", "required_docs", "submission_documents")),
        "duplicate_support_restriction": str(
            _first(row, "duplicate_support_restriction", "duplicate_restriction", default="") or ""
        ),
        "exclusion_conditions": _as_list(_first(row, "exclusion_conditions", "exclusions", "ineligible_conditions")),
        "source_name": source_name,
        "source_url": source_url,
        "source_date": source_date,
        "rule_version": str(_first(row, "rule_version", default="supabase-v1") or "supabase-v1"),
        "rule_review_status": str(
            _first(row, "rule_review_status", "review_status", default="Supabase imported") or "Supabase imported"
        ),
        "public_rule_scope": str(_first(row, "public_rule_scope", default="Supabase source data") or "Supabase source data"),
        "rule_limitations": _as_list(_first(row, "rule_limitations", "limitations"))
        or ["Unstructured fields require official document review"],
        "is_sample_data": bool(_first(row, "is_sample_data", default=False)),
        "notes": _build_notes(row),
    }
    return PolicyProduct(**item)


def load_policies_from_supabase() -> list[PolicyProduct]:
    _, _, table = _supabase_config()
    rows = _supabase_select(table)
    active_rows = [
        row for row in rows
        if row.get("is_active", True) is not False and row.get("deleted_at") in (None, "")
    ]
    return [_to_policy_product(row, idx) for idx, row in enumerate(active_rows, 1)]


def load_policies(path: Path | None = None) -> list[PolicyProduct]:
    if _use_supabase():
        return load_policies_from_supabase()
    path = path or get_policies_path()
    if not path.exists():
        raise FileNotFoundError(f"Policy data file not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [PolicyProduct(**item) for item in data]


def load_policies_from_upload(uploaded_file) -> list[PolicyProduct]:
    content = uploaded_file.read().decode("utf-8")
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(pd.io.common.StringIO(content))
        data = df.to_dict(orient="records")
        for item in data:
            for field in LIST_FIELDS:
                if field in item and isinstance(item[field], str):
                    item[field] = _as_list(item[field])
    else:
        data = json.loads(content)
    return [PolicyProduct(**item) for item in data]


def policies_to_dataframe(policies: list[PolicyProduct]) -> pd.DataFrame:
    return pd.DataFrame([p.model_dump() for p in policies])


def validate_policies(policies: list[PolicyProduct]) -> list[str]:
    errors = []
    ids = set()
    for p in policies:
        if not p.policy_id:
            errors.append(f"policy_id missing: {p.policy_name}")
        if p.policy_id in ids:
            errors.append(f"duplicate policy_id: {p.policy_id}")
        ids.add(p.policy_id)
        if not p.policy_name:
            errors.append("policy_name missing")
    return errors


def load_sample_cases() -> list[dict]:
    path = DATA_DIR / "sample_cases.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)
