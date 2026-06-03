from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE_URL = "https://aidp-i18ntt-sg.tiktok-row.net"
DEFAULT_MODEL = "gemini-3.1-fl"


@dataclass(frozen=True)
class ModelResponse:
    content: str
    model: str
    usage: dict[str, Any]
    raw: dict[str, Any]


class ModelHubClient:
    """Small OpenAI-compatible chat client for the internal ModelHub endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        thinking_budget: int = 0,
        timeout_seconds: int = 120,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.thinking_budget = thinking_budget
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "ModelHubClient":
        api_key = os.environ.get("MODELHUB_AK")
        if not api_key:
            raise SystemExit("MODELHUB_AK is required. Pass it as an environment variable; do not commit API keys.")
        return cls(
            api_key=api_key,
            base_url=os.environ.get("MODELHUB_BASE_URL", DEFAULT_BASE_URL),
            model=os.environ.get("MODELHUB_MODEL", DEFAULT_MODEL),
            thinking_budget=int(os.environ.get("MODELHUB_THINKING_BUDGET", "0")),
            timeout_seconds=int(os.environ.get("MODELHUB_TIMEOUT_SECONDS", "120")),
        )

    def chat(self, messages: list[dict[str, str]], max_tokens: int) -> ModelResponse:
        payload = {
            "stream": False,
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "thinking": {
                "include_thoughts": False,
                "budget_tokens": self.thinking_budget,
            },
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/modelhub/online/v2/crawl?ak={self.api_key}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-TT-LOGID": f"daily-briefing-agent-{int(time.time())}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw_text = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ModelHub HTTP {exc.code}: {detail}") from exc

        raw = json.loads(raw_text)
        content = raw["choices"][0]["message"]["content"]
        return ModelResponse(
            content=content,
            model=raw.get("model", self.model),
            usage=raw.get("usage", {}),
            raw=raw,
        )

