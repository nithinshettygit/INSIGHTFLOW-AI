"""Groq LLM intent detector with rule-based fallback."""

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
from app.engines.intent.rule_based import RuleBasedIntentDetector

logger = get_logger(__name__)

VALID_INTENTS = set(INTENT_TO_ENGINE.keys())


class LLMIntentDetector(IntentDetector):
    """Classify intent via Groq; fall back to rules on failure."""

    def __init__(
        self,
        settings: Settings | None = None,
        fallback: IntentDetector | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.fallback = fallback or RuleBasedIntentDetector()
        self._client: ChatGroq | None = None

    @property
    def available(self) -> bool:
        return bool(self.settings.groq_api_key.strip())

    def detect(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> IntentMatch:
        if not self.available:
            logger.warning("GROQ_API_KEY missing — using rule-based intent fallback")
            match = self.fallback.detect(query, context)
            return IntentMatch(
                intent=match.intent,
                target_engine=match.target_engine,
                confidence=match.confidence,
                matched_keywords=match.matched_keywords,
                rationale=match.rationale or "Fallback: Groq API key not configured",
                provider="rules_fallback",
                entities=match.entities,
            )

        try:
            return self._detect_with_groq(query, context)
        except Exception as exc:
            logger.exception("Groq intent classification failed: %s", exc)
            match = self.fallback.detect(query, context)
            return IntentMatch(
                intent=match.intent,
                target_engine=match.target_engine,
                confidence=match.confidence,
                matched_keywords=match.matched_keywords,
                rationale=f"Fallback after LLM error: {exc}",
                provider="rules_fallback",
                entities=match.entities,
            )

    def _detect_with_groq(
        self,
        query: str,
        context: dict[str, Any] | None,
    ) -> IntentMatch:
        client = self._get_client()
        messages = [
            SystemMessage(content=INTENT_SYSTEM_PROMPT),
            HumanMessage(content=build_user_prompt(query, context)),
        ]
        response = client.invoke(messages)
        content = response.content if isinstance(response.content, str) else str(response.content)
        payload = _parse_json_content(content)

        intent = str(payload.get("intent", "unknown")).lower().strip()
        if intent not in VALID_INTENTS:
            intent = "unknown"

        confidence_raw = payload.get("confidence", 0.5)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(confidence, 1.0))

        entities = payload.get("entities") or {}
        if not isinstance(entities, dict):
            entities = {}

        rationale = payload.get("rationale")
        if rationale is not None:
            rationale = str(rationale)

        logger.info(
            "LLM intent=%s confidence=%.3f provider=groq",
            intent,
            confidence,
        )
        return IntentMatch(
            intent=intent,  # type: ignore[arg-type]
            target_engine=INTENT_TO_ENGINE[intent],  # type: ignore[index]
            confidence=round(confidence, 3),
            matched_keywords=[],
            rationale=rationale,
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


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM response JSON must be an object")
    return data
