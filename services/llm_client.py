"""LLM client with optional OpenAI/Anthropic and template fallback."""

from __future__ import annotations

import json
import os
import re
from typing import Any


class LLMClient:
    def __init__(self):
        self.last_error: str = ""
        self.openai_key_present = bool(os.getenv("OPENAI_API_KEY"))
        self.use_anthropic = (
            os.getenv("USE_ANTHROPIC", "false").lower() == "true"
            and bool(os.getenv("ANTHROPIC_API_KEY"))
        )
        self.use_openai = (
            os.getenv("USE_OPENAI", "true").lower() == "true"
            and self.openai_key_present
        )
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL") or "claude-3-5-sonnet-20241022"
        self.openai_model = os.getenv("OPENAI_CHAT_MODEL") or "gpt-4o-mini"
        self.openai_base_url = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"

    def is_available(self) -> bool:
        return self.use_anthropic or self.use_openai

    def provider_name(self) -> str:
        if self.use_openai:
            return f"OpenAI/{self.openai_model}"
        if self.use_anthropic:
            return f"Anthropic/{self.anthropic_model}"
        return "template-fallback"

    def setup_message(self) -> str:
        if self.is_available():
            return f"GPT 연동: {self.provider_name()}"
        if not self.openai_key_present:
            return "GPT 연동: 비활성화 (.env의 OPENAI_API_KEY 필요)"
        return "GPT 연동: 비활성화"

    def generate_text(self, system_prompt: str, user_prompt: str) -> str | None:
        self.last_error = ""
        if self.use_anthropic:
            try:
                import anthropic

                client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                msg = client.messages.create(
                    model=self.anthropic_model,
                    max_tokens=2000,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return msg.content[0].text
            except Exception as e:
                self.last_error = f"Anthropic 호출 실패: {e}"
        if self.use_openai:
            try:
                import requests

                resp = requests.post(
                    f"{self.openai_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.openai_model,
                        "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.3,
                    },
                    timeout=45,
                )
                if resp.status_code >= 400:
                    self.last_error = f"OpenAI HTTP {resp.status_code}: {resp.text[:500]}"
                    return None
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                self.last_error = f"OpenAI 호출 실패: {e}"
        return None

    def _parse_json_text(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise

    def generate_json(self, system_prompt: str, user_prompt: str, schema_name: str = "") -> dict[str, Any]:
        text = self.generate_text(system_prompt + "\nRespond in valid JSON only.", user_prompt)
        if text:
            try:
                return self._parse_json_text(text)
            except Exception as e:
                self.last_error = f"JSON 파싱 실패: {e}"
        return {}
