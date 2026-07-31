"""AI Agent setup, API key management, client communication, and verdict response handling.

This module encapsulates:
1. Resolving DEDALUS_API_KEY from environment or local .env file.
2. HTTP client requests to the troll AI agent running on Dedalus Machine.
3. Response data parsing and formatting for AI-judged mini-games.
4. Server provisioning launcher via provision.py.
"""

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

GAME_DIR = Path(__file__).resolve().parent


def load_api_key() -> str:
    """Return DEDALUS_API_KEY, loading local .env file first."""
    load_dotenv(GAME_DIR / ".env")
    key = os.environ.get("DEDALUS_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DEDALUS_API_KEY not set. Add it to a .env file in this folder."
        )
    return key


class TrollBrain:
    """HTTP client for communicating with troll's FastAPI server on Dedalus."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout = timeout

    def judge(self, game_key: str, context: dict, submission: str) -> tuple[bool, str]:
        response = httpx.post(
            f"{self.base_url}/judge",
            headers=self.headers,
            json={"game_key": game_key, "context": context, "submission": submission},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return bool(data.get("passed", False)), str(data.get("reason") or "")


class AIAgent:
    """Manager for AI Agent server communication and verdict response processing."""

    def __init__(self, base_url: str, api_key: str):
        self.client = TrollBrain(base_url, api_key)

    @staticmethod
    def provision_server():
        """Provision fresh troll AI agent server on Dedalus Machine."""
        from provision import ensure_machine
        return ensure_machine()

    def process_judgment_response(
        self, game_key: str, context: dict[str, Any], submission: str
    ) -> tuple[bool, str]:
        """Process and structure AI agent response for AI-judged games."""
        cleaned_submission = (submission or "").strip()
        passed, raw_reason = self.client.judge(
            game_key=game_key,
            context=context,
            submission=cleaned_submission,
        )
        reason = (raw_reason or "").strip()
        if not reason:
            reason = "The troll grunts noncommittally."
        return bool(passed), reason
