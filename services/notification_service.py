"""Notification service with mock/live modes."""

from __future__ import annotations

import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

from models.report_schemas import NotificationPayload, NotificationSendResult, RequiredDocumentItem, ReviewReport
from models.schemas import BusinessCase
from services.llm_client import LLMClient
from utils.constants import CAUTION_MESSAGE
from utils.privacy import mask_phone_number

ROOT = Path(__file__).resolve().parents[1]


def _reload_env() -> None:
    load_dotenv(ROOT / ".env", override=True)


def _can_send_live() -> bool:
    _reload_env()
    return (
        os.getenv("NOTIFICATION_MODE", "mock").lower() == "live"
        and bool(os.getenv("SOLAPI_API_KEY"))
        and bool(os.getenv("SOLAPI_API_SECRET"))
        and bool(os.getenv("SOLAPI_SENDER"))
    )


def _can_send_email() -> bool:
    _reload_env()
    return (
        bool(os.getenv("SMTP_HOST", "").strip())
        and bool(os.getenv("SMTP_USERNAME", "").strip())
        and bool(os.getenv("SMTP_PASSWORD", "").strip())
        and bool(os.getenv("SMTP_FROM_EMAIL", "").strip())
    )


def _mask_email(email: str) -> str:
    if "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = local[:2] + "*" * min(5, len(local) - 2)
    return f"{masked_local}@{domain}"


def _is_gmail_host(host: str) -> bool:
    return "gmail.com" in (host or "").lower()


def _normalize_smtp_password(host: str, password: str) -> str:
    password = (password or "").strip()
    if _is_gmail_host(host):
        return password.replace(" ", "")
    return password


def _gmail_password_hint(host: str, password: str) -> str:
    if not _is_gmail_host(host):
        return ""
    compact_len = len((password or "").replace(" ", "").strip())
    if compact_len == 16:
        return ""
    return (
        "Gmail은 일반 계정 비밀번호가 아니라 2단계 인증 후 발급한 앱 비밀번호를 사용해야 합니다. "
        f"앱 비밀번호는 공백 제외 16자리인데 현재 SMTP_PASSWORD는 공백 제외 {compact_len}자리입니다."
    )


def _document_to_dict(item) -> dict:
    if isinstance(item, dict):
        return item
    model_dump = getattr(item, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return {
        "document_name": getattr(item, "document_name", "") or "필요서류",
        "reason": getattr(item, "reason", "") or "상담 결과 확인 필요",
        "required_for": getattr(item, "required_for", None),
        "priority": getattr(item, "priority", "") or "중간",
        "how_to_prepare": getattr(item, "how_to_prepare", None),
    }


def _normalize_required_documents(checklist: list) -> list[RequiredDocumentItem]:
    docs: list[RequiredDocumentItem] = []
    for item in checklist or []:
        data = _document_to_dict(item)
        try:
            docs.append(RequiredDocumentItem(**data))
        except Exception:
            docs.append(
                RequiredDocumentItem(
                    document_name=str(data.get("document_name") or "필요서류"),
                    reason=str(data.get("reason") or "상담 결과 확인 필요"),
                    required_for=data.get("required_for"),
                    priority=str(data.get("priority") or "중간"),
                    how_to_prepare=data.get("how_to_prepare"),
                )
            )
    return docs


def _enhance_message_with_llm(
    body: str,
    case: BusinessCase,
    report: ReviewReport,
    checklist: list[RequiredDocumentItem],
    message_type: str,
) -> str:
    checklist = _normalize_required_documents(checklist)
    client = LLMClient()
    if not client.is_available():
        return body
    system_prompt = (
        "너는 소상공인 정책금융 상담 후 고객에게 보낼 알림 메시지 초안을 작성한다. "
        "친절하고 짧게 쓰되, 승인·대출·보증 확정, 개인별 한도, 금리 확정 표현은 쓰지 않는다. "
        "상담자가 확인한 보고서 내용과 필요서류만 사용한다."
    )
    payload = {
        "message_type": message_type,
        "customer_name": case.customer_name,
        "business_name": case.business_name,
        "summary": report.counselor_summary,
        "policies_confirmed": report.recommended_policies,
        "policies_need_info": report.conditional_policies,
        "required_documents": [d.document_name for d in checklist[:8]],
        "next_actions": report.next_actions[:6],
        "caution": CAUTION_MESSAGE,
        "draft": body,
    }
    if message_type == "sms_short":
        length_rule = "220자 이내"
    elif message_type == "email":
        length_rule = "이메일 본문 형식"
    else:
        length_rule = "카카오 알림톡처럼 800자 이내"
    user_prompt = (
        f"아래 초안을 {length_rule}로 다시 작성해라. "
        "서류와 다음 행동을 빠뜨리지 말고, 마지막에 상담 참고용이라는 주의 문구를 포함해라.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )
    text = client.generate_text(system_prompt, user_prompt)
    return text.strip() if text and text.strip() else body


def build_notification_payload(
    case: BusinessCase,
    report: ReviewReport,
    checklist: list[RequiredDocumentItem],
    message_type: str = "kakao_mock",
) -> NotificationPayload:
    name = case.customer_name or "고객"
    docs = _normalize_required_documents(checklist)[:6]
    doc_lines = "\n".join(f"· {d.document_name}" for d in docs)

    if message_type == "sms_short":
        body = (
            f"[금융상담] {name}님, 오늘 상담 요약: {report.counselor_summary[:80]}... "
            f"준비서류: {', '.join(d.document_name for d in docs[:3])}. "
            f"{CAUTION_MESSAGE[:50]}..."
        )
        title = "[금융상담]"
    elif message_type == "email":
        body = (
            f"{name} 님, 안녕하세요.\n\n"
            f"오늘 상담 내용을 정리해 드립니다.\n{report.counselor_summary}\n\n"
            f"검토 방향: {', '.join(report.recommended_policies[:3])}\n\n"
            f"준비 서류:\n{doc_lines}\n\n"
            f"다음 행동:\n" + "\n".join(f"· {a}" for a in report.next_actions[:4]) + "\n\n"
            f"{CAUTION_MESSAGE}"
        )
        title = "소상공인 금융상담 안내"
    else:
        body = (
            f"[소상공인 금융상담 안내]\n"
            f"{name} 님, 안녕하세요.\n\n"
            f"📋 오늘 상담 요약\n{report.counselor_summary}\n\n"
            f"✅ 검토 가능 방향\n{', '.join(report.recommended_policies[:3])}\n\n"
            f"📎 준비 서류\n{doc_lines}\n\n"
            f"➡️ 다음 행동\n" + "\n".join(f"· {a}" for a in report.next_actions[:4]) + "\n\n"
            f"⚠️ {CAUTION_MESSAGE}"
        )
        title = "[소상공인 금융상담 안내]"

    body = _enhance_message_with_llm(body, case, report, checklist, message_type)

    return NotificationPayload(
        recipient_name=name,
        recipient_phone=None,
        recipient_email=None,
        message_type=message_type,
        message_title=title,
        message_body=body,
        required_documents=docs,
        application_links=["https://example.com/demo/apply"],
        caution_message=CAUTION_MESSAGE,
    )


def send_notification_mock(payload: NotificationPayload) -> NotificationSendResult:
    preview = {
        "to": mask_phone_number(payload.recipient_phone or ""),
        "title": payload.message_title,
        "body_preview": payload.message_body[:200] + "...",
        "type": payload.message_type,
    }
    return NotificationSendResult(
        success=True,
        mode="mock",
        provider="mock",
        message="Mock 발송 완료 (실제 발송되지 않음)",
        payload_preview=preview,
        )


def send_notification_email(payload: NotificationPayload) -> NotificationSendResult:
    _reload_env()
    recipient = (payload.recipient_email or "").strip()
    if not recipient:
        return NotificationSendResult(
            success=False,
            mode="live",
            provider="smtp",
            message="이메일 주소를 입력해 주세요.",
            payload_preview={},
        )
    if not _can_send_email():
        return NotificationSendResult(
            success=False,
            mode="live",
            provider="smtp",
            message="SMTP 환경변수가 설정되지 않아 실제 이메일을 보낼 수 없습니다.",
            payload_preview={"to": _mask_email(recipient), "title": payload.message_title},
        )

    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587") or "587")
    username = os.getenv("SMTP_USERNAME", "").strip()
    raw_password = os.getenv("SMTP_PASSWORD", "")
    password = _normalize_smtp_password(host, raw_password)
    from_email = os.getenv("SMTP_FROM_EMAIL", username).strip()
    from_name = os.getenv("SMTP_FROM_NAME", "소상공인 금융상담 AI 코파일럿").strip()
    use_ssl = os.getenv("SMTP_USE_SSL", "").strip().lower() in ("1", "true", "yes", "y")
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() not in ("0", "false", "no", "n")

    gmail_hint = _gmail_password_hint(host, raw_password)
    if gmail_hint:
        return NotificationSendResult(
            success=False,
            mode="live",
            provider="smtp",
            message=gmail_hint,
            payload_preview={"to": _mask_email(recipient), "title": payload.message_title},
        )

    message = EmailMessage()
    message["Subject"] = payload.message_title
    message["From"] = f"{from_name} <{from_email}>"
    message["To"] = recipient
    message.set_content(payload.message_body)

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                if use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(message)
        return NotificationSendResult(
            success=True,
            mode="live",
            provider="smtp",
            message="이메일 발송 완료",
            payload_preview={"to": _mask_email(recipient), "title": payload.message_title},
        )
    except smtplib.SMTPAuthenticationError as e:
        hint = _gmail_password_hint(host, raw_password)
        if not hint and _is_gmail_host(host):
            hint = (
                "Gmail SMTP 인증에 실패했습니다. SMTP_USERNAME이 발신 Gmail 주소와 같은지, "
                "2단계 인증이 켜져 있는지, SMTP_PASSWORD에 일반 비밀번호가 아닌 앱 비밀번호를 넣었는지 확인해 주세요."
            )
        message = hint or f"SMTP 인증 실패: {e}"
        return NotificationSendResult(
            success=False,
            mode="live",
            provider="smtp",
            message=message,
            payload_preview={"to": _mask_email(recipient), "title": payload.message_title},
        )
    except Exception as e:
        return NotificationSendResult(
            success=False,
            mode="live",
            provider="smtp",
            message=f"이메일 발송 오류: {e}",
            payload_preview={"to": _mask_email(recipient), "title": payload.message_title},
        )


def send_notification_live_solapi(payload: NotificationPayload) -> NotificationSendResult:
    if not _can_send_live():
        return NotificationSendResult(
            success=False,
            mode="live",
            provider="solapi",
            message="실제 발송 조건 미충족 (환경변수 확인 필요)",
            payload_preview={},
        )
    try:
        import requests

        api_key = os.getenv("SOLAPI_API_KEY")
        api_secret = os.getenv("SOLAPI_API_SECRET")
        sender = os.getenv("SOLAPI_SENDER")
        # Placeholder structure — actual Solapi API integration
        resp = requests.post(
            "https://api.solapi.com/messages/v4/send",
            json={
                "message": {
                    "to": payload.recipient_phone,
                    "from": sender,
                    "text": payload.message_body,
                }
            },
            headers={"Authorization": f"HMAC-SHA256 {api_key}"},
            timeout=10,
        )
        return NotificationSendResult(
            success=resp.status_code == 200,
            mode="live",
            provider="solapi",
            message=f"Solapi 응답: {resp.status_code}",
            payload_preview={"status": resp.status_code},
        )
    except Exception as e:
        return NotificationSendResult(
            success=False, mode="live", provider="solapi",
            message=f"발송 오류: {e}", payload_preview={},
        )
