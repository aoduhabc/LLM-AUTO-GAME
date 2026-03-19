from __future__ import annotations

import json
import os
import re
from urllib import error, request


class LlmClient:
    def __init__(self) -> None:
        self.api_key = (
            os.getenv("LLM_API_KEY", "").strip()
            or os.getenv("OPENAI_API_KEY", "").strip()
            or os.getenv("API_KEY", "").strip()
        )
        self.model = (
            os.getenv("LLM_MODEL", "").strip()
            or os.getenv("OPENAI_MODEL", "").strip()
            or "gpt-4o-mini"
        )
        explicit_llm_url = os.getenv("LLM_API_URL", "").strip()
        llm_base_url = (
            os.getenv("LLM_BASE_URL", "").strip()
            or os.getenv("OPENAI_BASE_URL", "").strip()
            or "https://api.openai.com/v1"
        )
        self.api_url = explicit_llm_url or self._build_chat_completions_url(llm_base_url)

    def call_json(self, system_prompt: str, user_prompt: str) -> dict | None:
        if not self.api_url or not self.api_key:
            return None
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payloads = [
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
                "response_format": {"type": "json_object"},
            },
            {
                "model": self.model,
                "messages": messages,
                "temperature": 0.7,
            },
        ]
        for payload in payloads:
            body = self._post(payload)
            if not body:
                continue
            parsed = self._parse_response_as_json(body)
            if parsed:
                return parsed
        return None

    def call_text(self, system_prompt: str, user_prompt: str) -> str | None:
        if not self.api_url or not self.api_key:
            return None
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        }
        body = self._post(payload)
        if not body:
            return None
        return self._parse_response_as_text(body)

    def _post(self, payload: dict) -> str | None:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as resp:
                return resp.read().decode("utf-8")
        except (error.URLError, TimeoutError, ValueError):
            return None

    def _parse_response_as_json(self, body: str) -> dict | None:
        try:
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            return None
        return self._parse_content_to_json(content)

    def _parse_response_as_text(self, body: str) -> str | None:
        try:
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            return None
        return self._flatten_content_to_text(content)

    def _parse_content_to_json(self, content: object) -> dict | None:
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            text_chunks = []
            for item in content:
                if isinstance(item, dict):
                    value = item.get("text")
                    if value:
                        text_chunks.append(str(value))
            content = "".join(text_chunks)
        if not isinstance(content, str):
            return None
        normalized = content.strip()
        if not normalized:
            return None
        try:
            parsed = json.loads(normalized)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            json_text = self._extract_json_object(normalized)
            if not json_text:
                return None
            try:
                parsed = json.loads(json_text)
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None

    def _flatten_content_to_text(self, content: object) -> str | None:
        if isinstance(content, str):
            normalized = content.strip()
            if not normalized:
                return None
            parsed_json = self._parse_content_to_json(normalized)
            if parsed_json:
                value = str(parsed_json.get("reply_text", "")).strip()
                return value or None
            return normalized
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, str):
                    value = item.strip()
                    if value:
                        chunks.append(value)
                elif isinstance(item, dict):
                    text = str(item.get("text", "")).strip()
                    if text:
                        chunks.append(text)
            joined = "".join(chunks).strip()
            if not joined:
                return None
            parsed_json = self._parse_content_to_json(joined)
            if parsed_json:
                value = str(parsed_json.get("reply_text", "")).strip()
                return value or None
            return joined
        if isinstance(content, dict):
            value = str(content.get("reply_text", "")).strip()
            return value or None
        return None

    def _extract_json_object(self, content: str) -> str | None:
        fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content, flags=re.IGNORECASE)
        for block in fenced_blocks:
            candidate = block.strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return content[start : end + 1].strip()
        return None

    def _build_chat_completions_url(self, base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if not normalized:
            return ""
        if normalized.endswith("/chat/completions"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/chat/completions"
        return f"{normalized}/v1/chat/completions"
