"""Groq LLM intent detector."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.engines.intent.base import INTENT_TO_ENGINE, IntentDetector, IntentMatch
from app.engines.intent.prompts import INTENT_SYSTEM_PROMPT, build_user_prompt

logger = get_logger(__name__)
VALID_INTENTS = set(INTENT_TO_ENGINE.keys())


class LLMIntentDetector(IntentDetector):
    """Classify a query through Groq and return its structured response."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: ChatGroq | None = None

    def detect(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> IntentMatch:
        if not self.settings.groq_api_key.strip():
            raise RuntimeError("GROQ_API_KEY is required for LLM intent detection")
        try:
            return self._detect_with_groq(query, context)
        except Exception as exc:
            logger.exception("Groq intent classification failed: %s", exc)
            raise RuntimeError(f"LLM intent detection failed: {exc}") from exc

    def _detect_with_groq(
        self,
        query: str,
        context: dict[str, Any] | None,
    ) -> IntentMatch:
        messages = [
            SystemMessage(content=INTENT_SYSTEM_PROMPT),
            HumanMessage(content=build_user_prompt(query, context)),
        ]
        response = self._get_client().invoke(messages)
        content = response.content if isinstance(response.content, str) else str(response.content)
        payload = _parse_json_content(content)

        intent = str(payload.get("intent", "unknown")).lower().strip()
        if intent not in VALID_INTENTS:
            intent = "unknown"
        confidence = _normalize_confidence(payload.get("confidence"))
        entities = payload.get("entities") if isinstance(payload.get("entities"), dict) else {}
        rationale = payload.get("rationale")

        logger.info("LLM intent=%s confidence=%.3f provider=groq", intent, confidence)
        return IntentMatch(
            intent=intent,  # type: ignore[arg-type]
            target_engine=INTENT_TO_ENGINE[intent],  # type: ignore[index]
            confidence=confidence,
            rationale=str(rationale) if rationale is not None else None,
            provider="groq",
            entities=entities,
        )

    def _get_client(self) -> ChatGroq:
        if self._client is None:
            self._client = ChatGroq(
                api_key=self.settings.groq_api_key,
                model=self.settings.groq_model,
                temperature=self.settings.intent_temperature,
            )
        return self._client


def _normalize_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.5
    return round(max(0.0, min(confidence, 1.0)), 3)


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    start = text.find("{")
    if start == -1:
        raise json.JSONDecodeError("No JSON object found", text, 0)

    # Decode one complete object so trailing explanations or duplicate model
    # responses do not make the valid first object fail with "Extra data".
    data, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(data, dict):
        raise ValueError("LLM response JSON must be an object")
    return data
