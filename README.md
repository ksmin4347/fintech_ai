# 소상공인 금융상담 AI 코파일럿

소상공인 금융상담자를 위한 Streamlit 기반 AI 상담 코파일럿 MVP입니다.

> "소상공인의 자금 고민을 근거 있는 상담과 실행 가능한 다음 행동으로 바꾸는 AI 상담 코파일럿"

이 서비스는 단순 지원사업 검색이 아니라, 상담 케이스 구조화 → 누락정보 탐지 → 정책조건 검토 → **RAG 상품 큐레이션** → **심사보고서·애프터케어**까지의 상담 흐름을 지원합니다.

## 주요 기능

### 기존 (기능 1)
- 상담 원문 구조화 (규칙 기반 + optional LLM)
- 누락정보 탐지 & Next Best Question
- 규칙 기반 정책조건 검토
- 자격격차 분석
- 상담기록 / 고객 안내문 생성

### 신규 (기능 2) RAG 상품 큐레이션
- 데모 정책 문서(Markdown) 기반 TF-IDF 검색 (API 키 불필요)
- 상담 케이스 + 정책 문서 근거 하이브리드 Top 3 큐레이션
- 검토 우선순위 점수 (승인 확률 아님)
- Evidence expander로 근거 문서 chunk 확인

### 신규 (기능 3) 심사보고서 & 애프터케어
- RM 심사 추천서 / 상담기록 / 기관 인계 메모 템플릿
- 필수 구비 서류 체크리스트
- 후속 관리 태스크
- 고객 알림 메시지 mock 미리보기 (기본 mock 모드)
- Markdown / JSON / CSV 다운로드

## 설치 방법

```bash
cd code
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

선택 기능 (OpenAI, Anthropic, Chroma, Pinecone):

```bash
pip install -r requirements-optional.txt
```

## 실행 방법

```bash
.\.venv\Scripts\activate
python -m streamlit run app.py
```

> **Windows 참고:** `streamlit run app.py`가 보안 정책으로 차단되면 `python -m streamlit run app.py`를 사용하세요.

브라우저: `http://localhost:8501`

## 데모 사용 흐름 (3분)

1. **1. 상담 입력** 탭 → 샘플 상담 불러오기 → 분석
2. **5. RAG 상품 큐레이션** 탭 → 큐레이션 실행
3. **7. 심사보고서 & 애프터케어** 탭 → 템플릿 선택 → 보고서 생성

> 상단 **번호 탭**으로 화면을 이동합니다. 코드 변경 후에는 Streamlit을 **반드시 재시작**하세요.

## 폴더 구조

```
code/
  app.py
  requirements.txt
  requirements-optional.txt
  data/
    policies_sample.json
    sample_cases.json
    policy_docs/          # RAG 데모 정책 문서 5건
    report_templates.json
    message_templates.json
  models/
    schemas.py
    rag_schemas.py
    report_schemas.py
  services/
    parser.py
    eligibility_engine.py
    rag_*.py               # RAG 파이프라인
    report_generator.py
    checklist_generator.py
    aftercare_manager.py
    notification_service.py
    llm_client.py
  utils/
    privacy.py
    dates.py
```

## 환경변수 (optional)

`.env.example` 참고. **API 키 없이도 전체 기능이 mock/TF-IDF 모드로 동작합니다.**

| 변수 | 설명 | 기본 |
|------|------|------|
| `USE_OPENAI` | OpenAI LLM/Embedding | false |
| `USE_ANTHROPIC` | Anthropic 보고서 생성 | false |
| `NOTIFICATION_MODE` | mock / live | mock |
| `SOLAPI_*` | 실제 SMS/알림톡 (live 시) | 없음 |

## Local / Mock 모드

- **RAG 검색:** scikit-learn TF-IDF (기본)
- **LLM:** template 기반 문장 생성 (API 없을 때)
- **알림 발송:** mock 미리보기만 (기본)
- **실제 발송:** `NOTIFICATION_MODE=live` + Solapi 키 + 고객 동의 체크 + 실제 발송 버튼

## 개인정보 주의사항

- 전화번호는 선택 입력, 미리보기에서 마스킹
- 실제 발송 전 **고객 동의 확인** 필수
- 상담 데이터는 로컬 세션에서만 처리 (MVP)
- 모든 결과는 **상담 참고용 초안**

## 정책 데이터

모든 정책 JSON·Markdown 문서는 `[데모]` 접두사가 붙은 **샘플 데이터**입니다. 실제 공식 공고와 다릅니다.

공공데이터 API(`DATA_GO_KR_API_KEY`)는 adapter만 준비되어 있으며, 실제 운영 시 endpoint 연결이 필요합니다.

## 향후 확장

- STT transcript 연동 (인터페이스: `case.transcript`)
- Chroma / Pinecone 벡터 DB
- 실제 정책공고 수집 파이프라인
- 상담 케이스 DB 저장
- OCR 기반 서류 추출

## 주의사항

- AI는 대출·보증 **승인을 확정하지 않습니다**
- "검토 가능", "조건부 검토", "제외 가능성", "판단 보류"만 사용
- 고객이 말하지 않은 정보는 "미확인"으로 표시
- 본 결과는 상담 참고용 초안이며, 최종 판단은 상담자가 공식 기준으로 수행해야 합니다
