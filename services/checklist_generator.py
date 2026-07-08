"""Required document checklist generator."""

from __future__ import annotations

from models.rag_schemas import CuratedPolicyRecommendation
from models.report_schemas import RequiredDocumentItem
from models.schemas import BusinessCase, EligibilityResult

BASE_DOCS = [
    ("사업자등록증", "사업자 신원 및 업종 확인", "공통", "높음", "사업자등록증 사본 준비"),
    ("대표자 신분증", "대표자 본인 확인", "공통", "높음", "주민등록증 또는 운전면허증"),
    ("개인정보 수집·이용 동의서", "신용조회 및 심사", "공통", "높음", "기관 양식 작성"),
]

CONDITIONAL_DOCS = {
    "연매출": ("최근 매출 증빙", "매출 기준 조건 검토", "매출 확인 상품", "중간", "부가세 과세표준증명 또는 매출장부"),
    "신용": ("신용조회 동의서", "신용 조건 검토", "신용 확인 상품", "높음", "NICE/KCB 조회 동의"),
    "보증": ("기존 보증 이용 내역", "중복지원 확인", "보증 상품", "중간", "보증확인서 또는 대출잔액 확인"),
    "시설": ("시설투자 견적서", "시설자금 심사", "시설자금 상품", "높음", "공사/장비 견적서"),
    "체납": ("국세·지방세 납세증명서", "체납 제외조건 확인", "공통", "높음", "홈택스/위택스 발급"),
    "매출감소": ("매출 감소 증빙", "긴급자금 심사", "긴급자금 상품", "높음", "전년 대비 매출 비교 자료"),
}


def generate_required_document_checklist(
    case: BusinessCase,
    recommendations: list[CuratedPolicyRecommendation],
    eligibility_results: list[EligibilityResult],
) -> list[RequiredDocumentItem]:
    seen: set[str] = set()
    items: list[RequiredDocumentItem] = []

    def add(name, reason, req_for, priority, how):
        if name in seen:
            return
        seen.add(name)
        items.append(RequiredDocumentItem(
            document_name=name, reason=reason, required_for=req_for,
            priority=priority, how_to_prepare=how,
        ))

    for name, reason, req_for, pri, how in BASE_DOCS:
        add(name, reason, req_for, pri, how)

    for rec in recommendations:
        for doc in rec.required_documents:
            add(doc, f"{rec.policy_name} 검토에 필요", rec.policy_name, "중간", "기관 공고 확인")

    if case.annual_revenue is None:
        add(*CONDITIONAL_DOCS["연매출"])
    if case.credit_band is None and case.credit_score is None:
        add(*CONDITIONAL_DOCS["신용"])
    if case.existing_guarantee in (None, "미확인"):
        add(*CONDITIONAL_DOCS["보증"])
    if case.funding_purpose and "시설" in str(case.funding_purpose):
        add(*CONDITIONAL_DOCS["시설"])
    if case.tax_arrears in (None, "미확인"):
        add(*CONDITIONAL_DOCS["체납"])
    if case.revenue_trend == "감소":
        add(*CONDITIONAL_DOCS["매출감소"])

    for er in eligibility_results:
        for doc in er.required_documents:
            add(doc, f"{er.policy_name} 조건검토", er.policy_name, "중간", "기관 양식 확인")

    return items
