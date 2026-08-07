"""Business Insight Engine — explanation, recommendations, root cause (Phase 10)."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.engines.insight.deterministic import build_deterministic_insight
from app.engines.insight.evidence import build_evidence_pack, infer_insight_mode
from app.engines.insight.prompts import INSIGHT_SYSTEM_PROMPT, build_insight_user_prompt
from app.schemas.insight import InsightMode
from app.schemas.profile import DatasetProfile

logger = get_logger(__name__)


class InsightEngineError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class InsightEngine:
    """Reason over processed evidence packs; LLM only for synthesis."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._llm: ChatGroq | None = None

    def analyze(
        self,
        *,
        meta: Any,
        question: str,
        mode: InsightMode | None,
        profile: DatasetProfile | None,
        frame: Any,
        focus_metrics: list[str],
        focus_dimensions: list[str],
        include_ml_context: bool,
        synthesize: bool | None,
    ) -> dict[str, Any]:
        cleaned = question.strip()
        if not cleaned:
            raise InsightEngineError("Question is required")

        resolved_mode: InsightMode = mode or infer_insight_mode(cleaned)  # type: ignore[assignment]
        if resolved_mode not in {"explanation", "recommendation", "root_cause"}:
            resolved_mode = "explanation"

        evidence = build_evidence_pack(
            meta=meta,
            profile=profile,
            frame=frame,
            focus_metrics=focus_metrics,
            focus_dimensions=focus_dimensions,
            include_ml_context=include_ml_context,
            settings=self.settings,
        )

        use_llm = (
            self.settings.insight_use_llm if synthesize is None else bool(synthesize)
        )
        if use_llm and self.settings.groq_api_key.strip():
            try:
                payload = self._synthesize_with_llm(
                    question=cleaned,
                    mode=resolved_mode,
                    evidence=evidence,
                )
                provider = "groq"
            except Exception as exc:
                logger.warning(
                    "Insight LLM synthesis failed, using deterministic fallback: %s",
                    exc,
                )
                payload = build_deterministic_insight(
                    question=cleaned,
                    mode=resolved_mode,
                    evidence=evidence,
                )
                provider = "deterministic_fallback"
        else:
            payload = build_deterministic_insight(
                question=cleaned,
                mode=resolved_mode,
                evidence=evidence,
            )
            provider = payload.get("provider") or "deterministic"

        logger.info(
            "Insight complete dataset_id=%s mode=%s provider=%s",
            getattr(meta, "dataset_id", None),
            resolved_mode,
            provider,
        )
        return {
            "dataset_id": getattr(meta, "dataset_id", None),
            "mode": resolved_mode,
            "question": cleaned,
            "headline": payload.get("headline") or "Business insight",
            "explanation": payload.get("explanation") or "",
            "findings": payload.get("findings") or [],
            "recommendations": payload.get("recommendations") or [],
            "root_causes": payload.get("root_causes") or [],
            "evidence": evidence,
            "provider": provider,
            "applied": {
                "mode": resolved_mode,
                "focus_metrics": (evidence.get("focus") or {}).get("metrics") or [],
                "focus_dimensions": (evidence.get("focus") or {}).get("dimensions")
                or [],
                "include_ml_context": include_ml_context,
                "synthesize": provider.startswith("groq"),
                "evidence_keys": sorted(evidence.keys()),
            },
        }

    def _synthesize_with_llm(
        self,
        *,
        question: str,
        mode: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        client = self._get_llm()
        messages = [
            SystemMessage(content=INSIGHT_SYSTEM_PROMPT),
            HumanMessage(
                content=build_insight_user_prompt(
                    question=question,
                    mode=mode,
                    evidence=evidence,
                )
            ),
        ]
        response = client.invoke(messages)
        content = getattr(response, "content", None)
        if isinstance(content, list):
            text = " ".join(str(part) for part in content)
        else:
            text = str(content or "")
        parsed = _parse_json_object(text)
        return {
            "headline": str(parsed.get("headline") or "Business insight"),
            "explanation": str(parsed.get("explanation") or ""),
            "findings": _normalize_findings(parsed.get("findings")),
            "recommendations": _normalize_recommendations(parsed.get("recommendations")),
            "root_causes": _normalize_root_causes(parsed.get("root_causes")),
        }

    def _get_llm(self) -> ChatGroq:
        if self._llm is None:
            self._llm = ChatGroq(
                api_key=self.settings.groq_api_key,
                model=self.settings.groq_model,
                temperature=self.settings.insight_temperature,
            )
        return self._llm


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        payload = json.loads(cleaned[start : end + 1])
        if isinstance(payload, dict):
            return payload
    raise InsightEngineError("LLM did not return valid insight JSON")


def _normalize_findings(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    for item in items[:8]:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "medium").lower()
        if severity not in {"low", "medium", "high"}:
            severity = "medium"
        title = str(item.get("title") or "").strip()
        detail = str(item.get("detail") or "").strip()
        if not title and not detail:
            continue
        normalized.append(
            {
                "title": title or "Finding",
                "detail": detail or title,
                "severity": severity,
            }
        )
    return normalized


def _normalize_recommendations(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "").strip()
        rationale = str(item.get("rationale") or "").strip()
        if not action:
            continue
        try:
            priority = int(item.get("priority") or 2)
        except (TypeError, ValueError):
            priority = 2
        priority = min(5, max(1, priority))
        normalized.append(
            {
                "action": action,
                "rationale": rationale or action,
                "priority": priority,
            }
        )
    return normalized


def _normalize_root_causes(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        cause = str(item.get("cause") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        if not cause:
            continue
        try:
            confidence = float(item.get("confidence") or 0.5)
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = min(1.0, max(0.0, confidence))
        normalized.append(
            {
                "cause": cause,
                "evidence": evidence or cause,
                "confidence": round(confidence, 3),
            }
        )
    return normalized
