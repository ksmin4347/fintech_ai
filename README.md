# 핀콕 : 소상공인 금융상담 AI 코파일럿

상담사가 소상공인 금융 상담을 더 빠르고 근거 있게 진행하도록 돕는 Streamlit 기반 AI 업무툴입니다.

핀콕은 상담 메모와 실시간 음성 상담 내용을 구조화하고, Supabase에 저장된 실제 지원정책 DB와 공개조건을 비교해 추천 근거, 비추천 근거, 자격 격차, 다음 행동, 신청 준비 패키지, 고객 안내문 발송까지 이어주는 상담 실행 코파일럿입니다.

> AI 결과는 상담 참고용 초안입니다. 최종 판단과 안내는 상담사가 공식 공고, 기관 기준, 고객 제출서류를 확인해 수행해야 합니다.

## GitHub

- Repository: <https://github.com/ksmin4347/fintech_ai>
- Main app file: `app.py`
- Streamlit Cloud entry point: `app.py`

## 핵심 기능

- 상담 입력: 고객명, 사업체명, 상담 원문, 상담 기준일을 입력합니다.
- 실시간 음성 상담: 녹음 버튼을 누르면 브라우저 음성인식으로 상담 내용을 받아쓰고, 상담 맥락을 바탕으로 고객·사업자 정보만 구조화합니다.
- GPT 구조화: 상담 메모에서 지역, 업종, 업력, 자금용도, 사업자 형태 등 필수 정보를 자동 추출합니다.
- 사람 확인: AI가 채운 정보와 미확인 정보를 상담사가 검토하고 수정할 수 있습니다.
- 정책 DB 연동: Supabase의 `announcements` 테이블 데이터를 기반으로 실제 정책 후보를 불러옵니다.
- 공개규칙 비교: 정책별 조건과 고객 정보를 비교해 확인 완료, 추가 확인 필요, 공개조건 불일치를 구분합니다.
- 점수와 근거: 추천 점수, 추천 근거, 비추천 근거, 확인이 필요한 조건을 함께 보여줍니다.
- 자격격차와 다음 행동: 고객이 어떤 자료를 준비해야 하는지 정책별로 정리합니다.
- 신청 준비 패키지: RM 심사 추천형, 기본 상담 기록형, 기관 인계 메모형 보고서를 생성합니다.
- 고객 안내문/발송: 고객용 안내문을 생성하고 SMTP 설정 시 실제 이메일 발송을 지원합니다.
- 상담사용/고객용 화면: 상담사는 전체 기능을 사용하고, 고객은 상담 진행률과 준비사항 중심의 화면을 볼 수 있습니다.

## 화면 구성

| 번호 | 화면 | 역할 |
| --- | --- | --- |
| 1 | 상담 입력 | 상담 메모 입력, 샘플 불러오기, 실시간 음성 받아쓰기 |
| 2 | 사람 확인·구조화 | AI가 추출한 고객·사업체 정보를 확인 |
| 3 | 누락정보 & 다음 질문 | 미확인 항목과 다음 질문 확인, 상담 정보 수정 |
| 4 | 공개규칙 비교 | 정책 DB의 조건과 고객 정보를 비교하고 점수 확인 |
| 5 | 자격격차 & 다음 행동 | 확인 완료 또는 추가 확인 정책별 다음 행동 정리 |
| 6 | 신청 준비 패키지 | 보고서 템플릿 선택, 준비서류와 신청 상태 정리 |
| 7 | 고객 안내문 / 발송 | 고객 안내문 생성, 문자 버튼, 이메일 실제 발송 |
| 8 | 정책 데이터 관리 | Supabase 정책 DB 로딩 상태와 정책 표 확인 |

## 보고서 템플릿

- RM 심사 추천형: 내부 심사자나 RM이 빠르게 판단할 수 있도록 추천 정책, 핵심 근거, 리스크, 보완사항을 중심으로 정리합니다.
- 기본 상담 기록형: 상담 내용을 표준 상담 기록처럼 남기는 양식입니다. 고객 정보, 상담 요약, 확인된 조건, 다음 안내를 균형 있게 담습니다.
- 기관 인계 메모형: 보증기관, 지자체, 팀원에게 전달할 때 필요한 최소 정보와 확인 요청사항을 간결하게 정리합니다.

## 프로젝트 구조

```text
code/
  app.py                         # Streamlit 진입점, 전역 상태와 화면 라우팅
  app_pages.py                   # 1~8번 화면 렌더링
  requirements.txt               # 기본 실행 의존성
  requirements-optional.txt      # 선택 의존성
  assets/
    fincoc_logo*.png             # 핀콕 로고 이미지
  components/
    realtime_speech/index.html   # 브라우저 실시간 음성인식 컴포넌트
  data/
    sample_cases.json            # 샘플 상담 케이스
    report_templates.json        # 보고서 템플릿 데이터
    message_templates.json       # 안내문 템플릿 데이터
  models/
    schemas.py                   # 상담, 정책, 결과 데이터 모델
  services/
    live_consultation.py         # 실시간 상담 텍스트 정리와 프로필 추출
    realtime_speech_component.py # Streamlit 음성 컴포넌트 연결
    policy_loader.py             # Supabase/local 정책 데이터 로더
    eligibility_engine.py        # 공개조건 비교 엔진
    readiness_package.py         # 신청 준비 패키지 생성
    notification_service.py      # 이메일/SMS 발송 서비스
  utils/
    constants.py                 # 서비스명, 탭 이름, 필수 필드
    ui_theme.py                  # 전역 UI 스타일
    brand_assets.py              # 로고 이미지 로딩
```

## 로컬 실행

```powershell
git clone https://github.com/ksmin4347/fintech_ai.git
cd fintech_ai
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m streamlit run app.py
```

브라우저에서 `http://localhost:8501`로 접속합니다.

Windows에서 `streamlit run app.py`가 막히면 아래처럼 실행합니다.

```powershell
python -m streamlit run app.py
```

## 환경변수 설정

`.env` 파일은 로컬 실행용입니다. `.env`와 실제 API 키는 절대 GitHub에 올리지 않습니다.

### OpenAI

```env
USE_OPENAI=true
OPENAI_API_KEY=your_openai_api_key
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

### Supabase 정책 DB

```env
POLICY_DATA_SOURCE=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_POLICY_TABLE=announcements
SUPABASE_POLICY_DOCUMENT_TABLE=
```

현재 앱은 `announcements` 테이블을 정책 DB로 사용하도록 구성되어 있습니다. 정책명은 `announcement_name` 계열 컬럼을 우선 활용하며, 로더가 정책 비교에 필요한 필드를 내부 모델로 정규화합니다.

### 이메일 발송

```env
NOTIFICATION_MODE=live
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_sender_gmail@gmail.com
SMTP_PASSWORD=your_16_digit_google_app_password
SMTP_FROM_EMAIL=your_sender_gmail@gmail.com
SMTP_FROM_NAME=핀콕 : 소상공인 금융상담 AI 코파일럿
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

Gmail은 일반 계정 비밀번호가 아니라 2단계 인증 후 발급한 16자리 앱 비밀번호를 사용해야 합니다.

### 문자 발송

현재 UI에는 문자 발송 버튼이 있으며, 기본값은 mock 모드입니다. 실제 문자 발송을 붙이려면 아래 값을 설정하고 발송 정책을 별도로 확인해야 합니다.

```env
SOLAPI_API_KEY=
SOLAPI_API_SECRET=
SOLAPI_SENDER=
```

## Streamlit Cloud 배포

1. GitHub에 최신 파일을 커밋하고 `main` 브랜치로 push합니다.
2. Streamlit Cloud에서 GitHub 저장소 `ksmin4347/fintech_ai`를 연결합니다.
3. Main file path는 `app.py`로 설정합니다.
4. Streamlit Cloud의 `Settings > Secrets`에 `.env`의 실제 값을 TOML 형식으로 입력합니다.
5. 저장 후 재부팅하면 배포 링크에 자동 반영됩니다.

예시:

```toml
USE_OPENAI = "true"
OPENAI_API_KEY = "..."
POLICY_DATA_SOURCE = "supabase"
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "..."
SUPABASE_POLICY_TABLE = "announcements"
NOTIFICATION_MODE = "live"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = "587"
SMTP_USERNAME = "..."
SMTP_PASSWORD = "..."
SMTP_FROM_EMAIL = "..."
SMTP_FROM_NAME = "핀콕 : 소상공인 금융상담 AI 코파일럿"
SMTP_USE_TLS = "true"
SMTP_USE_SSL = "false"
```

## 새 파일 커밋 시 주의

최근 기능 추가로 아래 파일과 폴더가 새로 생겼다면 함께 커밋해야 합니다.

```powershell
git add assets components services utils app.py app_pages.py requirements.txt README.md .gitignore .env.example
git commit -m "Update Fincoc consultation copilot"
git push -u origin main
```

단, `.env`, `.venv/`, `data/cache/`, `run_logs/`는 커밋하지 않습니다.

## 음성인식 사용 조건

- Chrome 또는 Edge 브라우저를 권장합니다.
- 마이크 권한을 허용해야 합니다.
- 로컬 실행에서는 `localhost`가 허용됩니다.
- 배포 환경에서는 HTTPS 주소에서 사용하는 것이 안정적입니다.
- 음성인식 결과는 브라우저 인식 품질에 영향을 받으므로, 앱 내부에서 금융 상담 맥락에 맞게 일부 표현을 보정합니다.

## 검증 명령

문법 오류를 빠르게 확인할 때:

```powershell
python -m py_compile app.py app_pages.py
```

앱 실행 확인:

```powershell
python -m streamlit run app.py
```

## 개인정보와 보안

- 고객 개인정보와 API 키는 GitHub에 올리지 않습니다.
- `.env`는 로컬 전용이고, 배포 환경에서는 Streamlit Cloud Secrets를 사용합니다.
- 이메일 실제 발송 전에는 고객의 수신 동의를 확인해야 합니다.
- AI가 생성한 상담 결과, 보고서, 안내문은 초안이며 최종 책임 판단은 상담사가 수행합니다.
