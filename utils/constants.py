"""Application constants."""

SERVICE_NAME = "핀콕 : 소상공인 금융상담 AI 코파일럿"
SERVICE_TAGLINE = "소상공인의 자금 고민을 근거 있는 상담과 실행 가능한 다음 행동으로 바꾸는 AI 상담 코파일럿"
DISCLAIMER = (
    "AI 결과는 상담 참고용입니다. 최종 판단은 상담자가 공식 기준과 고객 제출자료를 확인해 수행해야 합니다."
)
DOCUMENT_DISCLAIMER = (
    "본 안내는 상담 참고용 초안이며, 실제 신청 가능 여부와 세부 조건은 "
    "해당 기관의 최신 공식 공고 및 상담자 확인을 통해 최종 검토해야 합니다."
)
CAUTION_MESSAGE = DOCUMENT_DISCLAIMER
RAG_SCORE_LABEL = "검토 우선순위 점수"
DEMO_NOTICE = "현재 데이터는 데모용 샘플입니다."

UNKNOWN = "미확인"

FIELD_STATUS_OPTIONS = ["미확인", "추가 확인 필요", "확인됨", "서류 확인", "기관 확인"]

FIELD_SOURCE_OPTIONS = ["미확인", "고객 진술/상담 원문", "상담자 직접 입력", "제출서류", "기관 조회"]

DEFAULT_FIELD_SOURCE = "고객 진술/상담 원문"
DEFAULT_EVIDENCE_LOCATION = "상담 원문"

FIELD_BASIS_PERIOD = {
    "region": "상담일 현재",
    "business_type": "사업자등록증 기준",
    "industry": "사업자등록증 기준",
    "business_start_date": "사업자등록증 기준",
    "business_months": "상담 기준일 현재",
    "funding_purpose": "상담 발언 기준",
    "required_amount": "상담 발언 기준",
    "annual_revenue": "최근 1년",
    "monthly_revenue": "최근 월평균",
    "revenue_trend": "최근 매출 흐름",
    "credit_score": "상담일 현재",
    "credit_band": "상담일 현재",
    "existing_guarantee": "상담일 현재",
    "existing_loan": "상담일 현재",
    "tax_arrears": "상담일 현재",
    "business_status": "상담일 현재",
    "collateral": "상담일 현재",
    "requested_timeline": "상담 발언 기준",
    "special_notes": "상담 발언 기준",
}

REQUIRED_FIELDS = [
    ("region", "사업장 지역", "지역별 보증상품 검토 필요", "사업장 소재지가 어느 시·도인가요?"),
    ("business_type", "사업자 형태", "개인사업자·법인사업자 등 대상 조건 확인 필요", "사업자 형태가 개인사업자입니까, 법인사업자입니까?"),
    ("industry", "업종", "업종별 지원 조건 확인 필요", "사업자등록증상 업종이 무엇인가요?"),
    ("business_months", "업력", "업력 제한 조건 확인 필요", "사업을 시작한 날짜가 언제인가요?"),
    ("funding_purpose", "자금 용도", "자금용도별 상품 매칭 필요", "필요한 자금은 운영비 목적입니까, 시설투자 목적입니까?"),
    ("required_amount", "필요 자금 규모", "한도 조건 검토 필요", "필요한 자금 규모는 대략 얼마인가요?"),
    ("annual_revenue", "연매출", "매출 기준 조건 확인 필요", "최근 1년 기준 대략적인 연매출은 얼마인가요?"),
    ("credit_band", "신용구간", "신용 조건 검토 필요", "NICE 또는 KCB 신용평점 구간을 알고 계신가요?"),
    ("existing_guarantee", "기존 보증 이용 여부", "중복지원 제한 확인 필요", "기존에 지역신용보증재단 보증을 이용한 적이 있습니까?"),
    ("existing_loan", "기존 정책자금 이용 여부", "중복지원 제한 확인 필요", "기존에 정책자금을 이용한 적이 있습니까?"),
    ("tax_arrears", "세금 체납 여부", "제외조건 확인 필요", "현재 세금 체납이 있으신가요?"),
    ("business_status", "휴폐업 여부", "사업 지속 여부 확인 필요", "현재 사업을 정상 운영 중이신가요?"),
]

STATUS_COLORS = {
    "검토 가능": "#28a745",
    "조건부 검토": "#007bff",
    "제외 가능성": "#fd7e14",
    "판단 보류": "#6c757d",
}

STATUS_ICONS = {
    "검토 가능": "✅",
    "조건부 검토": "🔵",
    "제외 가능성": "⚠️",
    "판단 보류": "⏸️",
}

INDUSTRY_KEYWORDS = {
    "카페": "카페/음식점",
    "음식점": "카페/음식점",
    "커피": "카페/음식점",
    "미용실": "미용/서비스",
    "헤어": "미용/서비스",
    "도소매": "도소매",
    "소매": "도소매",
    "온라인": "온라인쇼핑몰",
    "쇼핑몰": "온라인쇼핑몰",
    "제조": "제조업",
    "학원": "교육서비스",
}

REGION_KEYWORDS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]

FUNDING_PURPOSE_KEYWORDS = {
    "운영자금": "운영자금",
    "운영비": "운영자금",
    "운영 자금": "운영자금",
    "시설자금": "시설자금",
    "시설투자": "시설자금",
    "인테리어": "시설자금",
    "창업자금": "창업자금",
    "창업": "창업자금",
    "긴급": "긴급경영안정자금",
    "경영안정": "긴급경영안정자금",
}
