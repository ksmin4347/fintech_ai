"""UI helpers and visual theme for the Streamlit app."""

from __future__ import annotations

import html
from datetime import date

import streamlit as st

from models.schemas import BusinessCase
from services.status_mapper import map_policy_status
from utils.brand_assets import brand_logo_data_uri
from utils.constants import SERVICE_NAME
from utils.profile_progress import structured_profile_progress


ACCENT_BLUE = "#2563EB"
ACCENT_GREEN = "#16A34A"

WORKFLOW_STAGES = [
    ("상담 접수", "상담 입력과 AI 구조화", ("1. 상담 입력", "2. 사람 확인·구조화")),
    ("규칙 검토", "누락정보, 공개규칙, 점수", ("3. 누락정보 & 다음 질문", "4. 공개규칙 비교")),
    ("실행 준비", "격차, 보고서, 고객 안내", ("5. 자격격차 & 다음 행동", "6. 신청 준비 패키지", "7. 고객 안내문 / 발송")),
    ("운영 데이터", "정책 DB와 규칙표 관리", ("8. 정책 데이터 관리",)),
]


def inject_global_styles() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --app-bg: #F7F8FA;
            --panel: #ffffff;
            --line: #E5E7EB;
            --soft-line: #F1F5F9;
            --text-main: #111827;
            --text-sub: #6B7280;
            --text-faint: #9CA3AF;
            --blue: {ACCENT_BLUE};
            --green: {ACCENT_GREEN};
            --amber: #D97706;
            --red: #DC2626;
            --purple: #7C3AED;
            --blue-soft: #EFF6FF;
            --green-soft: #ECFDF5;
            --amber-soft: #FFFBEB;
            --red-soft: #FEF2F2;
            --purple-soft: #F5F3FF;
            --top-nav: #1F2D49;
            --top-nav-height: 60px;
        }}
        html, body, [class*="css"] {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo",
                "Noto Sans KR", "Malgun Gothic", sans-serif;
            color: var(--text-main);
            letter-spacing: 0;
        }}
        html {{
            scroll-padding-top: 86px;
        }}
        .stApp {{
            background: var(--app-bg);
        }}
        [data-testid="stHeader"] {{
            background: var(--top-nav) !important;
            border-bottom: 1px solid rgba(255, 255, 255, .08);
            box-shadow: none;
        }}
        [data-testid="stHeader"] [data-testid="stToolbar"],
        [data-testid="stHeader"] [data-testid="stToolbarActions"],
        [data-testid="stHeader"] [data-testid="stAppDeployButton"],
        [data-testid="stHeader"] [data-testid="stMainMenu"] {{
            background: transparent !important;
            color: #e5edf8 !important;
        }}
        [data-testid="stHeader"] button,
        [data-testid="stHeader"] button p,
        [data-testid="stHeader"] [data-testid="stIconMaterial"] {{
            color: #e5edf8 !important;
        }}
        [data-testid="stHeader"] button:hover {{
            background: rgba(255, 255, 255, .10) !important;
            color: #ffffff !important;
        }}
        [data-testid="stHeader"] [data-testid="stStatusWidget"],
        [data-testid="stHeader"] [data-testid="stStatusWidget"] *,
        [data-testid="stStatusWidget"],
        [data-testid="stStatusWidget"] * {{
            color: #ffffff !important;
        }}
        [data-testid="stHeader"] svg,
        [data-testid="stStatusWidget"] svg,
        [data-testid="stHeader"] [data-testid="stIconMaterial"],
        [data-testid="stStatusWidget"] [data-testid="stIconMaterial"] {{
            color: #ffffff !important;
        }}
        [data-testid="stHeader"] svg path[fill="none"],
        [data-testid="stStatusWidget"] svg path[fill="none"] {{
            fill: none !important;
            stroke: none !important;
        }}
        [data-testid="stHeader"] img,
        [data-testid="stHeader"] canvas,
        [data-testid="stStatusWidget"] img,
        [data-testid="stStatusWidget"] canvas {{
            background: transparent !important;
            filter: none !important;
            opacity: 1 !important;
        }}
        [data-testid="stSkeleton"],
        [data-testid*="Skeleton" i],
        [aria-busy="true"],
        div[class*="Skeleton"],
        div[class*="skeleton"],
        div[class*="stSkeleton"] {{
            background: #ffffff !important;
            border: 1px solid #CBD5E1 !important;
            border-radius: 8px !important;
            box-shadow: 0 10px 26px rgba(15, 23, 42, .12) !important;
            overflow: hidden;
        }}
        [data-testid="stSkeleton"] *,
        [data-testid*="Skeleton" i] *,
        [aria-busy="true"] *,
        div[class*="Skeleton"] *,
        div[class*="skeleton"] *,
        div[class*="stSkeleton"] *,
        [data-testid="stSkeleton"]::before,
        [data-testid="stSkeleton"]::after,
        [data-testid*="Skeleton" i]::before,
        [data-testid*="Skeleton" i]::after,
        [aria-busy="true"]::before,
        [aria-busy="true"]::after,
        div[class*="Skeleton"]::before,
        div[class*="Skeleton"]::after,
        div[class*="skeleton"]::before,
        div[class*="skeleton"]::after,
        div[class*="stSkeleton"]::before,
        div[class*="stSkeleton"]::after {{
            background-color: #ffffff !important;
            background-image: linear-gradient(
                90deg,
                #ffffff 0%,
                #EEF2F7 45%,
                #ffffff 85%
            ) !important;
        }}
        [data-testid="stSpinner"] {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: #ffffff !important;
            border: 1px solid #e2eaf3;
            border-radius: 8px;
            padding: 9px 12px;
            box-shadow: 0 8px 22px rgba(15, 23, 42, .08);
        }}
        .block-container {{
            max-width: 1440px;
            padding-top: 3.6rem;
            padding-bottom: 3.5rem;
            overflow: visible;
        }}
        h1, h2, h3, h4 {{
            letter-spacing: 0;
            color: var(--text-main);
        }}
        h2, h3 {{
            margin-top: .35rem;
        }}
        [data-testid="stSidebar"],
        [data-testid="stSidebarContent"] {{
            background:
                linear-gradient(
                    180deg,
                    var(--top-nav) 0,
                    var(--top-nav) var(--top-nav-height),
                    #FFFFFF var(--top-nav-height),
                    #FFFFFF 100%
                ) !important;
        }}
        [data-testid="stSidebar"] {{
            border-right: 0;
            position: relative;
        }}
        [data-testid="stSidebar"]::after {{
            content: "";
            position: absolute;
            top: 0;
            right: 0;
            bottom: 0;
            width: 1px;
            background: var(--line);
            pointer-events: none;
            z-index: 2;
        }}
        [data-testid="stSidebar"] > div {{
            position: relative;
            z-index: 3;
        }}
        [data-testid="stSidebar"] > div:first-child {{
            padding-top: 1.1rem;
            padding-left: 1.25rem;
            padding-right: 1.25rem;
        }}
        [data-testid="stSidebarHeader"],
        [data-testid="stSidebarHeader"] *,
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stSidebarCollapseButton"] button {{
            background: transparent !important;
        }}
        [data-testid="stSidebarHeader"],
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stSidebarCollapseButton"] button,
        [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"] {{
            color: #e5edf8 !important;
        }}
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{
            color: var(--text-sub);
        }}
        .sidebar-brand {{
            border: 1px solid var(--line);
            border-radius: 10px;
            background: #ffffff;
            padding: 15px 14px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
        }}
        .sidebar-brand-top {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }}
        .sidebar-logo {{
            width: 50px;
            height: 50px;
            flex: 0 0 50px;
            border-radius: 12px;
            background: #ffffff;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            box-shadow: inset 0 0 0 1px var(--line);
            overflow: hidden;
        }}
        .sidebar-logo img {{
            width: 44px;
            height: 44px;
            object-fit: contain;
            display: block;
        }}
        .sidebar-eyebrow {{
            color: var(--blue);
            font-size: 11px;
            font-weight: 850;
            letter-spacing: .04em;
        }}
        .sidebar-brand-title {{
            color: var(--text-main);
            font-size: 16px;
            font-weight: 900;
            line-height: 1.28;
            margin-top: 2px;
            word-break: keep-all;
            overflow-wrap: normal;
        }}
        .sidebar-brand-desc {{
            color: var(--text-sub);
            font-size: 13px;
            line-height: 1.55;
        }}
        .sidebar-section {{
            color: var(--text-faint);
            font-size: 12px;
            font-weight: 850;
            letter-spacing: .02em;
            margin: 18px 0 8px;
        }}
        .sidebar-status-card {{
            border: 1px solid var(--line);
            border-radius: 10px;
            background: #ffffff;
            padding: 12px 13px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .03);
        }}
        .sidebar-status-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            padding: 8px 0;
            border-bottom: 1px solid var(--soft-line);
        }}
        .sidebar-status-row:last-child {{
            border-bottom: 0;
        }}
        .sidebar-status-label {{
            color: var(--text-sub);
            font-size: 12px;
            font-weight: 750;
        }}
        .sidebar-status-value {{
            color: var(--text-main);
            font-size: 12px;
            font-weight: 850;
            text-align: right;
        }}
        .sidebar-dot {{
            width: 7px;
            height: 7px;
            border-radius: 999px;
            display: inline-block;
            margin-right: 6px;
            background: var(--green);
            box-shadow: 0 0 0 3px rgba(22, 163, 74, .12);
        }}
        .sidebar-dot.muted {{
            background: #a0a8b3;
            box-shadow: 0 0 0 3px rgba(160, 168, 179, .12);
        }}
        .sidebar-notice {{
            border: 1px solid var(--line);
            border-radius: 10px;
            background: #F9FAFB;
            color: var(--text-sub);
            padding: 12px 13px;
            font-size: 12px;
            line-height: 1.5;
        }}
        [data-testid="stSidebar"] .stButton > button {{
            width: 100%;
            border-radius: 10px;
            min-height: 46px;
            background: #ffffff;
            border: 1px solid var(--line);
            color: var(--text-main);
            font-weight: 850;
        }}
        [data-testid="stSidebar"] .stButton > button:hover {{
            color: var(--blue);
            border-color: rgba(37, 99, 235, .44);
            background: var(--blue-soft);
        }}
        [data-testid="stSidebar"] [data-testid="stSelectbox"] {{
            margin-top: -4px;
        }}
        [data-testid="stSidebar"] div[data-testid="stAlert"] {{
            font-size: 12px;
        }}
        .app-topbar {{
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #ffffff;
            padding: 18px 18px 17px;
            margin-bottom: 14px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
        }}
        .app-title-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 18px;
        }}
        .app-title-row > div:first-child {{
            flex: 1 1 430px;
            min-width: 260px;
        }}
        .app-kicker {{
            color: var(--blue);
            font-size: 11px;
            font-weight: 850;
            letter-spacing: .06em;
            margin-bottom: 6px;
        }}
        .app-brand-title {{
            display: flex;
            align-items: center;
            gap: 12px;
            min-width: 0;
        }}
        .app-logo {{
            width: 62px;
            height: 58px;
            object-fit: contain;
            flex: 0 0 auto;
            display: block;
        }}
        .app-title {{
            font-size: 24px;
            font-weight: 850;
            line-height: 1.22;
            margin: 0;
            word-break: keep-all;
        }}
        .app-topbar .app-title {{
            color: var(--text-main);
        }}
        .app-subtitle {{
            color: var(--text-sub);
            font-size: 15px;
            margin-top: 7px;
        }}
        .app-topbar .app-subtitle {{
            color: var(--text-sub);
        }}
        .case-meta {{
            display: flex;
            flex-wrap: wrap;
            flex: 1 1 360px;
            justify-content: flex-end;
            gap: 8px;
            min-width: 0;
            padding-top: 2px;
        }}
        .chip {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            height: 32px;
            padding: 0 11px;
            border-radius: 999px;
            background: #F9FAFB;
            border: 1px solid var(--line);
            color: var(--text-sub);
            font-size: 12px;
            font-weight: 700;
            white-space: nowrap;
        }}
        .chip strong {{
            color: var(--text-main);
            font-weight: 800;
        }}
        .chip.ai-review {{
            background: var(--purple-soft);
            border-color: #DDD6FE;
            color: #5B21B6;
        }}
        .chip.ai-review strong {{
            color: #5B21B6;
        }}
        .workflow-strip {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 8px;
            margin: 10px 0 12px 0;
        }}
        .workflow-step {{
            min-height: 62px;
            border-radius: 10px;
            border: 1px solid var(--line);
            background: #ffffff;
            padding: 11px 12px;
        }}
        .workflow-step.active {{
            border-color: rgba(37, 99, 235, .38);
            background: var(--blue-soft);
            box-shadow: inset 3px 0 0 var(--blue);
        }}
        .workflow-label {{
            font-size: 13px;
            font-weight: 850;
            color: var(--text-main);
            margin-bottom: 4px;
        }}
        .workflow-desc {{
            color: var(--text-sub);
            font-size: 12px;
            line-height: 1.35;
        }}
        .metric-row {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 8px;
            margin: 8px 0 14px;
        }}
        .structure-progress {{
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #ffffff;
            padding: 14px 15px 15px;
            margin: 8px 0 10px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
        }}
        .structure-progress-head {{
            display: flex;
            align-items: flex-end;
            justify-content: space-between;
            gap: 14px;
            margin-bottom: 10px;
        }}
        .structure-progress-title {{
            color: var(--text-main);
            font-size: 15px;
            font-weight: 850;
        }}
        .structure-progress-note {{
            color: var(--text-sub);
            font-size: 12px;
            margin-top: 3px;
        }}
        .structure-progress-percent {{
            color: var(--blue);
            font-size: 26px;
            line-height: 1;
            font-weight: 900;
            white-space: nowrap;
        }}
        .structure-progress-track {{
            position: relative;
            height: 9px;
            border-radius: 999px;
            overflow: hidden;
            background: #EEF2F7;
        }}
        .structure-progress-fill {{
            height: 100%;
            border-radius: 999px;
            background: var(--blue);
            box-shadow: none;
        }}
        .structure-progress-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 10px;
        }}
        .structure-progress-tag {{
            border-radius: 999px;
            border: 1px solid var(--line);
            background: #F9FAFB;
            color: var(--text-sub);
            font-size: 12px;
            font-weight: 750;
            padding: 5px 9px;
            white-space: nowrap;
        }}
        .mini-metric {{
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #ffffff;
            padding: 13px 14px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .03);
        }}
        .mini-label {{
            color: var(--text-sub);
            font-size: 12px;
            font-weight: 700;
            margin-bottom: 5px;
        }}
        .mini-value {{
            color: var(--text-main);
            font-size: 23px;
            font-weight: 850;
            line-height: 1.1;
        }}
        .mini-note {{
            color: var(--text-faint);
            font-size: 12px;
            margin-top: 5px;
        }}
        div[data-testid="stMetric"] {{
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 12px 14px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .03);
        }}
        div[data-testid="stMetric"] label {{
            color: var(--text-sub) !important;
            font-weight: 700;
        }}
        .stButton > button {{
            border-radius: 10px;
            border: 1px solid var(--line);
            min-height: 42px;
            font-weight: 800;
            box-shadow: none;
            background: #ffffff;
            color: var(--text-main);
        }}
        .stButton > button:hover {{
            border-color: var(--blue);
            color: var(--blue);
        }}
        .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
            background: var(--blue);
            border-color: var(--blue);
            color: #ffffff;
        }}
        div[data-testid="stRadio"] {{
            overflow: visible !important;
            padding: 6px 0 12px 0;
            margin: 0 0 6px 0;
        }}
        div[data-testid="stRadio"] > div {{
            overflow: visible !important;
        }}
        div[data-testid="stRadio"] label[data-baseweb="radio"] {{
            min-height: 38px;
            display: inline-flex;
            align-items: center;
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 8px 12px;
            margin-right: 5px;
            margin-bottom: 6px;
            box-shadow: none;
        }}
        div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {{
            background: var(--blue-soft);
            border-color: rgba(37, 99, 235, .42);
            color: var(--blue);
            font-weight: 800;
        }}
        div[data-testid="stRadio"] label[data-testid="stRadioOption"][data-selected="true"] {{
            font-weight: 900 !important;
            color: var(--text-main) !important;
        }}
        div[data-testid="stRadio"] label[data-testid="stRadioOption"][data-selected="true"] * {{
            font-weight: 900 !important;
        }}
        div[data-testid="stRadio"] label:has(input:checked),
        div[data-testid="stRadio"] label:has(input[aria-checked="true"]),
        div[data-testid="stRadio"] [role="radio"][aria-checked="true"] {{
            font-weight: 900 !important;
            color: var(--text-main) !important;
        }}
        div[data-testid="stRadio"] label:has(input:checked) *,
        div[data-testid="stRadio"] label:has(input[aria-checked="true"]) *,
        div[data-testid="stRadio"] [role="radio"][aria-checked="true"] *,
        div[data-testid="stRadio"] [aria-checked="true"] p {{
            font-weight: 900 !important;
        }}
        [data-testid="stDataFrame"], [data-testid="stDataEditor"] {{
            border: 1px solid var(--line);
            border-radius: 12px;
            overflow: hidden;
            background: #ffffff;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .03);
        }}
        [data-testid="stExpander"] {{
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #ffffff;
        }}
        [data-testid="stTextArea"] textarea, [data-testid="stTextInput"] input {{
            border-radius: 10px;
        }}
        div[data-testid="stAlert"] {{
            border-radius: 10px;
            border-width: 1px;
        }}
        .policy-card {{
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #ffffff;
            padding: 15px 16px;
            margin: 10px 0 8px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .03);
        }}
        .policy-card-title {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            font-weight: 850;
            font-size: 16px;
        }}
        .policy-card-sub {{
            color: var(--text-sub);
            margin-top: 5px;
            font-size: 13px;
        }}
        .status-pill {{
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 5px 9px;
            font-size: 11px;
            font-weight: 800;
            color: var(--blue);
            background: var(--blue-soft);
            white-space: nowrap;
        }}
        .status-pill.green {{
            color: #15803D;
            background: var(--green-soft);
        }}
        .status-pill.yellow {{
            color: #92400E;
            background: var(--amber-soft);
        }}
        .status-pill.red {{
            color: var(--red);
            background: var(--red-soft);
        }}
        .status-pill.gray {{
            color: #4B5563;
            background: #F3F4F6;
        }}
        .section-caption {{
            color: var(--text-sub);
            font-size: 13px;
            margin-top: -4px;
            margin-bottom: 12px;
        }}
        .view-mode-note {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin: 4px 0 10px;
            padding: 10px 12px;
            border: 1px solid var(--line);
            border-radius: 12px;
            background: #ffffff;
            color: var(--text-sub);
            font-size: 13px;
        }}
        .customer-hero {{
            border: 1px solid #D6E4F5;
            border-radius: 16px;
            background:
                linear-gradient(135deg, rgba(37, 99, 235, .10) 0%, rgba(20, 184, 166, .08) 100%),
                #ffffff;
            padding: 22px 24px;
            margin: 12px 0 18px;
            box-shadow: 0 14px 36px rgba(31, 45, 73, .08);
        }}
        .customer-hero-top {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 20px;
        }}
        .customer-kicker {{
            color: var(--blue);
            font-size: 12px;
            font-weight: 900;
            letter-spacing: .05em;
            margin-bottom: 6px;
        }}
        .customer-title {{
            color: var(--text-main);
            font-size: 28px;
            font-weight: 900;
            line-height: 1.25;
        }}
        .customer-subtitle {{
            color: var(--text-sub);
            font-size: 15px;
            line-height: 1.55;
            margin-top: 7px;
        }}
        .customer-percent {{
            min-width: 116px;
            text-align: right;
            color: var(--blue);
            font-size: 36px;
            font-weight: 950;
            line-height: 1;
        }}
        .customer-bar {{
            width: 100%;
            height: 13px;
            border-radius: 999px;
            background: #EAF0F7;
            overflow: hidden;
            margin-top: 18px;
        }}
        .customer-bar-fill {{
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, #2563EB 0%, #14B8A6 100%);
        }}
        .customer-chip-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 14px;
        }}
        .customer-chip {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            border: 1px solid #DDE7F3;
            border-radius: 999px;
            background: rgba(255, 255, 255, .78);
            padding: 7px 10px;
            color: #475467;
            font-size: 12px;
            font-weight: 800;
        }}
        .customer-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin: 14px 0;
        }}
        .customer-grid.two {{
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .customer-card {{
            border: 1px solid var(--line);
            border-radius: 14px;
            background: #ffffff;
            padding: 16px 17px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
        }}
        .customer-card.soft {{
            background: #FBFCFE;
        }}
        .customer-card-title {{
            color: #344054;
            font-size: 13px;
            font-weight: 850;
            margin-bottom: 8px;
        }}
        .customer-card-value {{
            color: var(--text-main);
            font-size: 22px;
            font-weight: 900;
            line-height: 1.25;
            word-break: keep-all;
            overflow-wrap: anywhere;
        }}
        .customer-card-desc {{
            color: var(--text-sub);
            font-size: 13px;
            line-height: 1.5;
            margin-top: 6px;
        }}
        .customer-section-title {{
            color: var(--text-main);
            font-size: 22px;
            font-weight: 900;
            margin: 26px 0 10px;
        }}
        .customer-steps {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin: 12px 0 16px;
        }}
        .customer-step {{
            border: 1px solid #DDE7F3;
            border-radius: 14px;
            background: #ffffff;
            padding: 14px;
        }}
        .customer-step.done {{
            border-color: rgba(22, 163, 74, .30);
            background: linear-gradient(180deg, #ffffff 0%, #F0FDF4 100%);
        }}
        .customer-step.active {{
            border-color: rgba(37, 99, 235, .38);
            background: linear-gradient(180deg, #ffffff 0%, #EFF6FF 100%);
        }}
        .customer-step-label {{
            color: var(--text-main);
            font-size: 14px;
            font-weight: 900;
        }}
        .customer-step-desc {{
            color: var(--text-sub);
            font-size: 12px;
            line-height: 1.45;
            margin-top: 4px;
        }}
        .customer-policy {{
            border: 1px solid #DDE7F3;
            border-radius: 14px;
            background: #ffffff;
            padding: 16px;
            margin-bottom: 10px;
        }}
        .customer-policy-top {{
            display: flex;
            justify-content: space-between;
            gap: 14px;
        }}
        .customer-policy-name {{
            color: var(--text-main);
            font-size: 16px;
            font-weight: 900;
            line-height: 1.4;
        }}
        .customer-policy-meta {{
            color: var(--text-sub);
            font-size: 13px;
            margin-top: 4px;
        }}
        .customer-score {{
            min-width: 72px;
            text-align: right;
            color: var(--blue);
            font-size: 24px;
            font-weight: 950;
        }}
        .customer-list {{
            margin: 0;
            padding-left: 18px;
            color: #344054;
            line-height: 1.6;
            font-size: 14px;
        }}
        @media (max-width: 900px) {{
            .app-title-row {{
                flex-direction: column;
                align-items: flex-start;
            }}
            .case-meta {{
                justify-content: flex-start;
                min-width: 0;
            }}
            .workflow-strip,
            .metric-row {{
                grid-template-columns: 1fr;
            }}
            .block-container {{
                padding-left: 1rem;
                padding-right: 1rem;
            }}
            .customer-hero-top {{
                flex-direction: column;
            }}
            .customer-percent {{
                text-align: left;
            }}
            .customer-grid,
            .customer-grid.two,
            .customer-steps {{
                grid-template-columns: 1fr;
            }}
            .customer-policy-top {{
                flex-direction: column;
            }}
            .customer-score {{
                text-align: left;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_case_header(
    case: BusinessCase,
    active_tab: str,
    *,
    analyzed: bool,
    parser_mode: str,
    missing_count: int,
    policy_count: int,
) -> None:
    customer = html.escape(case.customer_name or "고객 미입력")
    business = html.escape(case.business_name or "사업체 미입력")
    tab_name = html.escape(active_tab.split(". ", 1)[-1])
    parser = html.escape(parser_mode or "대기")
    status = "분석 완료" if analyzed else "분석 전"
    consultation_date = case.consultation_date or date.today()
    service_name = html.escape(SERVICE_NAME)
    brand_logo = brand_logo_data_uri("fincoc_logo.png")
    st.markdown(
        f"""
        <div class="app-topbar">
            <div class="app-title-row">
                <div>
                    <div class="app-kicker">POLICY FINANCE COPILOT</div>
                    <div class="app-brand-title">
                        <img class="app-logo" src="{brand_logo}" alt="fincoc 로고" />
                        <div class="app-title">{service_name}</div>
                    </div>
                    <div class="app-subtitle">{customer} · {business} · {tab_name}</div>
                </div>
                <div class="case-meta">
                    <span class="chip ai-review"><strong>AI 초안 · 상담자 검토 필요</strong></span>
                    <span class="chip"><strong>{status}</strong></span>
                    <span class="chip">구조화 <strong>{parser}</strong></span>
                    <span class="chip">미확인 <strong>{missing_count}</strong></span>
                    <span class="chip">정책 <strong>{policy_count}</strong></span>
                    <span class="chip">기준일 <strong>{consultation_date}</strong></span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_workflow_strip(active_tab: str) -> None:
    cards = []
    for title, desc, tabs in WORKFLOW_STAGES:
        active = " active" if active_tab in tabs else ""
        cards.append(
            f'<div class="workflow-step{active}">'
            f'<div class="workflow-label">{html.escape(title)}</div>'
            f'<div class="workflow-desc">{html.escape(desc)}</div>'
            "</div>"
        )
    st.markdown(f"<div class=\"workflow-strip\">{''.join(cards)}</div>", unsafe_allow_html=True)


def render_quality_metrics(
    case: BusinessCase,
    missing_count: int,
    policy_count: int,
    eligibility_results: list | None = None,
    recommendation_count: int = 0,
) -> None:
    progress = structured_profile_progress(case)
    total = int(progress["total"])
    confirmed = int(progress["confirmed"])
    needs_review = int(progress["needs_review"])
    partial = int(progress["partial"])
    percent = int(progress["percent"])
    st.markdown(
        f"""
        <div class="structure-progress">
            <div class="structure-progress-head">
                <div>
                    <div class="structure-progress-title">상담 프로필 구조화</div>
                    <div class="structure-progress-note">필수 항목 {confirmed}/{total} · 보완 {needs_review}</div>
                </div>
                <div class="structure-progress-percent">{percent}%</div>
            </div>
            <div class="structure-progress-track">
                <div class="structure-progress-fill" style="width: {percent}%;"></div>
            </div>
            <div class="structure-progress-meta">
                <span class="structure-progress-tag">확인 {confirmed}</span>
                <span class="structure-progress-tag">추가 확인 {needs_review}</span>
                <span class="structure-progress-tag">값 있음·미확인 {partial}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    results = eligibility_results or []
    actionable_count = sum(
        1
        for result in results
        if map_policy_status(result.final_status) in ("확인 완료", "추가 확인 필요")
    )
    candidate_count = recommendation_count or actionable_count
    cards = [
        ("확인된 정보", str(confirmed), "13개 구조화 항목 기준"),
        ("추가 확인", str(needs_review), "미확인·보완 필요 항목"),
        ("추천 후보", str(candidate_count), "확인 완료·추가 확인 정책"),
        ("정책 DB", str(policy_count), "현재 불러온 전체 정책"),
    ]
    html_cards = []
    for label, value, note in cards:
        html_cards.append(
            '<div class="mini-metric">'
            f'<div class="mini-label">{html.escape(label)}</div>'
            f'<div class="mini-value">{html.escape(value)}</div>'
            f'<div class="mini-note">{html.escape(note)}</div>'
            "</div>"
        )
    st.markdown(f"<div class=\"metric-row\">{''.join(html_cards)}</div>", unsafe_allow_html=True)


def policy_card_html(title: str, institution: str, status: str, reason: str, *, rank: int | None = None, score: int | None = None) -> str:
    heading = html.escape(title)
    prefix = f"#{rank} " if rank else ""
    score_text = f" · 점수 {score}" if score is not None else ""
    if status == "확인 완료":
        pill_class = "status-pill green"
    elif status == "추가 확인 필요":
        pill_class = "status-pill yellow"
    elif status == "공개조건 불일치":
        pill_class = "status-pill red"
    else:
        pill_class = "status-pill"
    return (
        '<div class="policy-card">'
        '<div class="policy-card-title">'
        f"<span>{html.escape(prefix)}{heading}</span>"
        f'<span class="{pill_class}">{html.escape(status)}{html.escape(score_text)}</span>'
        "</div>"
        f'<div class="policy-card-sub">{html.escape(institution)} · {html.escape(reason or "상세 조건 확인 필요")}</div>'
        "</div>"
    )
