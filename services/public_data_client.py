"""Public data API adapter (optional)."""

from __future__ import annotations

import os


class PublicDataPolicyClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("DATA_GO_KR_API_KEY")

    def fetch_policy_items(self, query: str | None = None) -> list[dict]:
        if not self.api_key:
            return []
        # MVP: placeholder for data.go.kr integration
        return []

    def status_message(self) -> str:
        if not self.api_key:
            return "공공데이터 API 키가 없습니다. 샘플 정책 문서를 사용합니다."
        return "공공데이터 API 연동 준비됨 (MVP에서는 샘플 데이터 사용)"
