"""Rule-based intent detector (Phase 4 fallback / offline mode)."""

from __future__ import annotations

import re
from typing import Any

from app.core.logging import get_logger
from app.engines.intent.base import IntentDetector, IntentMatch
from app.engines.intent.rules import INTENT_RULES

logger = get_logger(__name__)


class RuleBasedIntentDetector(IntentDetector):
    """Classify queries with deterministic keyword/phrase rules.

    Used as primary detector when INTENT_PROVIDER=rules, otherwise as
    fallback when Groq is unavailable.
    """

    def __init__(self, rules=INTENT_RULES, unknown_threshold: float = 0.35) -> None:
        self.rules = rules
        self.unknown_threshold = unknown_threshold

    def detect(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> IntentMatch:
        _ = context  # Context reserved for future rule enrichment.
        normalized = _normalize(query)
        if not normalized:
            return IntentMatch(
                intent="unknown",
                target_engine="none",
                confidence=0.0,
                matched_keywords=[],
                provider="rules",
            )

        scores: dict[str, float] = {}
        priorities: dict[str, int] = {}
        matched: dict[str, list[str]] = {}
        engines: dict[str, str] = {}

        for rule in self.rules:
            hits = [kw for kw in rule.keywords if kw in normalized]
            if not hits:
                continue

            # Longer phrases contribute slightly more signal.
            phrase_bonus = sum(max(len(kw.split()) - 1, 0) * 0.15 for kw in hits)
            score = (len(hits) * rule.weight) + phrase_bonus
            intent = rule.intent
            scores[intent] = scores.get(intent, 0.0) + score
            priorities[intent] = max(priorities.get(intent, 0), rule.priority)
            engines[intent] = rule.target_engine
            matched.setdefault(intent, [])
            for kw in hits:
                if kw not in matched[intent]:
                    matched[intent].append(kw)

        if not scores:
            logger.debug("No intent rules matched for query=%r", query)
            return IntentMatch(
                intent="unknown",
                target_engine="none",
                confidence=0.0,
                matched_keywords=[],
                provider="rules",
            )

        best_intent = max(
            scores.keys(),
            key=lambda intent: (scores[intent], priorities.get(intent, 0)),
        )
        raw_score = scores[best_intent]
        confidence = min(raw_score / (raw_score + 2.0), 0.99)

        if confidence < self.unknown_threshold:
            logger.debug(
                "Intent confidence below threshold (%.2f < %.2f) for query=%r",
                confidence,
                self.unknown_threshold,
                query,
            )
            return IntentMatch(
                intent="unknown",
                target_engine="none",
                confidence=round(confidence, 3),
                matched_keywords=matched.get(best_intent, []),
                provider="rules",
            )

        result = IntentMatch(
            intent=best_intent,  # type: ignore[arg-type]
            target_engine=engines[best_intent],  # type: ignore[arg-type]
            confidence=round(confidence, 3),
            matched_keywords=matched.get(best_intent, []),
            provider="rules",
        )
        logger.info(
            "Detected intent=%s engine=%s confidence=%.3f keywords=%s",
            result.intent,
            result.target_engine,
            result.confidence,
            result.matched_keywords,
        )
        return result


def _normalize(query: str) -> str:
    text = query.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text
